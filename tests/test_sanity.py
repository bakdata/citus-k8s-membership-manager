import typing
import pytest
import psycopg2
import logging
import requests
import retrying
import time

from config import (
    NAMESPACE,
    WORKER_NAME,
    MASTER_NAME,
    WORKER_COUNT,
    YAML_DIR,
    CONFIG_MAP,
    READINESS_WAIT,
)
from util import run_local_query, PortForwarder, parse_single_kubernetes_yaml
from kubernetes import client

log = logging.getLogger(__file__)

MAX_TIMEOUT = 60 * 1000


@pytest.fixture()
def stop_provisioning(kubernetes_client):
    _scale_pod(WORKER_NAME, 1, kubernetes_client)
    time.sleep(READINESS_WAIT + 10)  # Wait for pod readiness
    yield
    _scale_pod(WORKER_NAME, WORKER_COUNT, kubernetes_client)


@pytest.fixture()
def replace_citus_nodes(kubernetes_client):
    _scale_pod(WORKER_NAME, 0, kubernetes_client)
    log.info("Wait for worker scale down")
    time.sleep(60)  # Wait for DELETED pod events
    _scale_pod(MASTER_NAME, 0, kubernetes_client)
    log.info("Wait for master scale down")
    time.sleep(90)
    _scale_pod(WORKER_NAME, WORKER_COUNT, kubernetes_client)
    _scale_pod(MASTER_NAME, 1, kubernetes_client)
    yield
    time.sleep(90)  # Wait for scale up
    time.sleep(READINESS_WAIT)  # Wait for readiness checks to be finished


@pytest.mark.incremental
def test_wait_for_workers_before_provisioning(stop_provisioning):
    @retrying.retry(
        stop_max_attempt_number=20,
        wait_fixed=1000,
        retry_on_exception=lambda e: isinstance(e, UnboundLocalError)
        or isinstance(e, ProcessLookupError),
    )
    def check_provisioning(pod_name: str):
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            with pytest.raises(psycopg2.ProgrammingError):
                run_local_query("SELECT one();", 5435)

    check_provisioning(MASTER_NAME + "-0")
    check_provisioning(WORKER_NAME + "-0")


@pytest.mark.incremental
def test_wait_for_worker_readiness(replace_citus_nodes):
    assert len(_get_workers_within_cluster()) == 0
    assert len(_get_masters_within_cluster()) == 0


@pytest.mark.incremental
def test_node_provisioning_with_configmap():
    def check_query_result(pod_name: str, query: str, result: int) -> None:
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            assert result == run_local_query(query, 5435)[0][0]

    @retrying.retry(stop_max_delay=MAX_TIMEOUT, wait_fixed=1 * 1000)
    def check_provisioning() -> None:
        master_query = "SELECT one();"
        check_query_result(MASTER_NAME + "-0", master_query, 1)
        worker_query = "SELECT two();"
        for i in range(WORKER_COUNT):
            check_query_result(WORKER_NAME + "-{}".format(i), worker_query, 2)

    check_provisioning()


@pytest.mark.incremental
def test_initial_registration():
    @retrying.retry(
        stop_max_delay=MAX_TIMEOUT,
        wait_fixed=1 * 1000,
        retry_on_exception=lambda e: isinstance(
            e, requests.exceptions.RequestException
        ),
        retry_on_result=lambda r: len(r) < 2,
    )
    def registered_workers() -> typing.List[str]:
        return _get_workers_within_cluster()

    assert set(registered_workers()) == set([WORKER_NAME + "-0", WORKER_NAME + "-1"])


@pytest.mark.incremental
def test_distributed_table_exists_on_all_workers():
    schema = "public"
    expected_table = "eventstore"

    def match_tables(tables: typing.List[typing.Tuple]) -> None:
        assert any(t[2].startswith(expected_table) for t in tables)

    for i in range(WORKER_COUNT):
        tables = _get_tables_in_schema(WORKER_NAME + "-{}".format(i), schema)
        match_tables(tables)


def test_db_master_knows_workers():
    @retrying.retry(
        stop_max_delay=MAX_TIMEOUT,
        wait_fixed=1 * 1000,
        retry_on_result=lambda r: len(r) < 2,
    )
    def registered_on_master() -> typing.List[typing.Tuple]:
        return _get_registered_workers()

    assert len(registered_on_master()) == 2


def test_node_provisioning_with_config_update():
    worker_query = (
        "CREATE FUNCTION three() RETURNS integer AS 'select 3;' LANGUAGE SQL;"
    )
    master_query = "CREATE FUNCTION four() RETURNS integer AS 'select 4;' LANGUAGE SQL;"
    config_map = parse_single_kubernetes_yaml(YAML_DIR + "provision-map.yaml")
    config_map["data"]["master.setup"] = master_query
    config_map["data"]["worker.setup"] = worker_query
    log.info("Updating config map: %s", config_map)
    log.info(
        client.CoreV1Api().patch_namespaced_config_map(
            CONFIG_MAP, NAMESPACE, config_map
        )
    )
    master_test = "SELECT four();"
    worker_test = "SELECT three();"

    def check_query_result(pod_name: str, test_query: str, test_result: int) -> None:
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            assert test_result == run_local_query(test_query, 5435)[0][0]

    @retrying.retry(stop_max_delay=2 * MAX_TIMEOUT, wait_fixed=1 * 1000)
    def check_provisioning() -> None:
        check_query_result(MASTER_NAME + "-0", master_test, 4)
        for i in range(WORKER_COUNT):
            check_query_result(WORKER_NAME + "-{}".format(i), worker_test, 3)

    check_provisioning()


def test_unregister_worker(kubernetes_client):
    _scale_pod(WORKER_NAME, 1, kubernetes_client)

    @retrying.retry(stop_max_delay=MAX_TIMEOUT, wait_fixed=1 * 1000)
    def check_state_after_scaling() -> None:
        assert len(_get_workers_within_cluster()) == 1
        assert len(_get_registered_workers()) == 1

    check_state_after_scaling()


def _scale_pod(pod_name: str, count: int, kubernetes_client: client.AppsV1Api) -> None:
    log.info("Scale %s to %s", pod_name, count)
    patch_body = {"spec": {"replicas": count}}
    resp = kubernetes_client.patch_namespaced_stateful_set_scale(
        pod_name, NAMESPACE, patch_body
    )
    log.info(resp)


def _get_workers_within_cluster() -> typing.List[str]:
    return _request_registered_pods()["workers"]


def _get_masters_within_cluster() -> typing.List[str]:
    return _request_registered_pods()["masters"]


@retrying.retry(stop_max_delay=MAX_TIMEOUT, wait_fixed=5 * 1000)
def _request_registered_pods() -> typing.Dict[str, typing.List]:
    with PortForwarder("deployment/citus-manager", (5000, 5000), NAMESPACE):
        log.info("Request registered pods")
        response = requests.get("http://localhost:5000/registered").json()
        log.info("Registered pods: %s", response)
    return response


def _get_registered_workers() -> typing.List[typing.Tuple]:
    with PortForwarder(MASTER_NAME + "-0", (5435, 5432), NAMESPACE):
        rows = run_local_query("SELECT master_get_active_worker_nodes();", 5435)
        log.info("Currently registered worker nodes: %s", rows)
        return rows


def _get_tables_in_schema(pod_name: str, schema: str) -> typing.List[typing.Tuple]:
    query = "SELECT * FROM information_schema.tables WHERE table_schema = '{}'".format(
        schema
    )
    with PortForwarder(pod_name, (5436, 5432), NAMESPACE):
        rows = run_local_query(query, 5436)
        log.info("Current tables: %s in schema %s on %s", rows, schema, pod_name)
        return rows
