import typing
import pytest
import psycopg2
import logging
import requests
import retrying
import time

from config import (
    NAMESPACE,
    PG_CONF,
    WORKER_NAME,
    MASTER_NAME,
    WORKER_COUNT,
    YAML_DIR,
    CONFIG_MAP,
)
from util import run_local_query, PortForwarder, parse_single_kubernetes_yaml
from kubernetes import client

log = logging.getLogger(__file__)

MAX_TIMEOUT = 60 * 1000


@pytest.fixture()
def stop_provisioning(kubernetes_client):
    _scale_pod(WORKER_NAME, 1, kubernetes_client)

    def patch_pod(pod_name: str) -> None:
        client.CoreV1Api().patch_namespaced_pod(pod_name, NAMESPACE, {})

    try:
        patch_pod(WORKER_NAME)
        patch_pod(MASTER_NAME)
        time.sleep(10)  # Wait for pod readiness
    except client.rest.ApiException as e:
        log.error(e)
    yield
    _scale_pod(WORKER_NAME, 2, kubernetes_client)


def test_wait_for_worker_readiness():
    pass


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
    query = "CREATE FUNCTION three() RETURNS integer AS 'select 3;' LANGUAGE SQL;"
    config_map = parse_single_kubernetes_yaml(YAML_DIR + "provision-map.yaml")
    config_map["data"]["master.setup"] = query
    config_map["data"]["worker.setup"] = query
    log.info("Updating config map: %s", config_map)
    client.CoreV1Api().patch_namespaced_config_map(CONFIG_MAP, NAMESPACE, config_map)

    def check_query_result(pod_name: str) -> None:
        test_query = "SELECT three();"
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            assert 3 == run_local_query(test_query, 5435)[0][0]

    @retrying.retry(stop_max_delay=2 * MAX_TIMEOUT, wait_fixed=1 * 1000)
    def check_provisioning() -> None:
        check_query_result(MASTER_NAME + "-0")
        for i in range(WORKER_COUNT):
            check_query_result(WORKER_NAME + "-{}".format(i))

    check_provisioning()


def test_unregister_worker(kubernetes_client):
    _scale_pod(WORKER_NAME, 1, kubernetes_client)

    @retrying.retry(stop_max_delay=MAX_TIMEOUT, wait_fixed=1 * 1000)
    def check_state_after_scaling() -> None:
        assert len(_get_workers_within_cluster()) == 1
        assert len(_get_registered_workers()) == 1

    check_state_after_scaling()


def _scale_pod(pod_name: str, count: int, kubernetes_client: client.AppsV1Api) -> None:
    patch_body = {"spec": {"replicas": count}}
    kubernetes_client.patch_namespaced_stateful_set_scale(
        WORKER_NAME, NAMESPACE, patch_body
    )


def _get_workers_within_cluster() -> typing.List[str]:
    with PortForwarder("deployment/citus-manager", (5000, 5000), NAMESPACE):
        response = requests.get("http://localhost:5000/registered").json()["workers"]
        log.info("Registered workers: %s", response)
    return response


def _get_registered_workers() -> typing.List[typing.Tuple]:
    with PortForwarder(MASTER_NAME + "-0", (5435, 5432), NAMESPACE):
        rows = run_local_query("SELECT master_get_active_worker_nodes();", 5435)
        log.info("Currently registered worker nodes: %s", rows)
        return rows
