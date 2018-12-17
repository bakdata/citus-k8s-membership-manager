import typing
import subprocess
import logging
import os
import signal
import requests
import time
import retrying
import psycopg2
import pytest

from contextlib import contextmanager
from config import NAMESPACE, PG_CONF, WORKER_NAME, MASTER_NAME, WORKER_COUNT
from kubernetes import client

log = logging.getLogger(__file__)

MAX_TIMEOUT = 60 * 1000


def test_wait_for_workers_before_provisioning(kubernetes_client):
    _scale_pod(WORKER_NAME, 1, kubernetes_client)

    def patch_pod(pod_name: str) -> None:
        client.CoreV1Api().patch_namespaced_pod(pod_name, NAMESPACE, {})

    try:
        patch_pod(WORKER_NAME)
        patch_pod(MASTER_NAME)
    except client.rest.ApiException as e:
        log.error(e)

    @retrying.retry(retry_on_exception=lambda e: isinstance(e, UnboundLocalError))
    def check_provisioning(pod_name: str):
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            with pytest.raises(psycopg2.ProgrammingError):
                _run_local_query("SELECT one();", 5435)

    time.sleep(10)  # Wait for pod readiness
    check_provisioning(MASTER_NAME + "-0")
    check_provisioning(WORKER_NAME + "-0")
    _scale_pod(WORKER_NAME, 2, kubernetes_client)


def test_node_provisioning_with_configmap():
    def check_query_result(pod_name: str, query: str, result: int) -> None:
        with PortForwarder(pod_name, (5435, 5432), NAMESPACE):
            assert result == _run_local_query(query, 5435)[0][0]

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
        response = requests.get("http://localhost:5000/registered").json()
        log.info("Registered workers: %s", response)
    return response


def _get_registered_workers() -> typing.List[typing.Tuple]:
    with PortForwarder(MASTER_NAME + "-0", (5435, 5432), NAMESPACE):
        rows = _run_local_query("SELECT master_get_active_worker_nodes();", 5435)
        log.info("Currently registered worker nodes: %s", rows)
        return rows


def _run_local_query(query: str, port: int) -> typing.List[typing.Tuple]:
    with db_connector(port) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()


@contextmanager
def db_connector(port: int) -> typing.Iterator[psycopg2._psycopg.connection]:
    try:
        conn = psycopg2.connect(
            dbname=PG_CONF["db"], host="localhost", user=PG_CONF["user"], port=port
        )
        yield conn
    finally:
        conn.close()


class PortForwarder:
    def __init__(
        self, pod_name: str, port_mapping: typing.Tuple[int, int], namespace: str
    ) -> None:
        cmd = "kubectl port-forward {} {}:{} -n {}"
        self.status_cmd = "kubectl get pods --all-namespaces | grep {}".format(pod_name)

        self.cmd = cmd.format(pod_name, port_mapping[0], port_mapping[1], namespace)

    def __enter__(self) -> None:
        log.info(
            "Pod status: %s",
            subprocess.run(
                [self.status_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            ).stdout,
        )
        self.pid = subprocess.Popen(self.cmd.split(" ")).pid
        time.sleep(1)  # Wait until port forwarding is established
        log.info("Port forwarding created with %s in process %s", self.cmd, self.pid)

    def __exit__(self, *args) -> None:
        os.kill(self.pid, signal.SIGTERM)
