import sys
import logging
import typing
import pytest
import os
import subprocess
import time

from kubernetes import config, client
from config import NAMESPACE, POD_NAMES, YAML_DIR, MANAGER_DEPLOYMENT


LOCAL = os.environ.get("DEVELOPMENT", True)

logging.basicConfig(
    format="[%(asctime)s|%(name)s-%(funcName)s(%(lineno)d)|%(levelname)s]: %(message)s",
    level="INFO",
    stream=sys.stdout,
)

log = logging.getLogger(__file__)


@pytest.fixture(scope="session")
def namespace():
    try:
        path = YAML_DIR + "default_namespace.yaml"
        _create_deployments(path)
        yield _set_context_namespace(NAMESPACE)
    finally:
        body = client.V1DeleteOptions()
        client.CoreV1Api().delete_namespace(NAMESPACE, body)
        _set_context_namespace("default")


@pytest.fixture(scope="session")
def manager_service_account(kubernetes_client, namespace):
    try:
        name = "pod-listing-sa"
        path = YAML_DIR + "pods-list-role-binding.yaml"

        def create_role_binding() -> None:
            cmd = "kubectl apply -f {}".format(path)
            _run_kubectl_command(cmd)

        yield create_role_binding()
    finally:
        body = client.V1DeleteOptions()
        client.CoreV1Api().delete_namespaced_service_account(name, NAMESPACE, body)
        client.RbacAuthorizationV1Api().delete_cluster_role("pods-list", body)
        client.RbacAuthorizationV1Api().delete_cluster_role_binding("pods-list", body)


@pytest.fixture(scope="session")
def kubernetes_client():
    config.load_kube_config()
    return client.AppsV1Api()


@pytest.fixture(scope="session", autouse=True)
def setup_cluster(kubernetes_client, manager_service_account):
    try:
        citus_worker = YAML_DIR + "citus-worker.yaml"
        citus_master = YAML_DIR + "citus-master.yaml"
        _create_deployments(MANAGER_DEPLOYMENT)
        _create_deployments(citus_master)
        log.info("Wait until master is running")
        time.sleep(3)  # TODO: wait until at least one master is running
        yield _create_deployments(citus_worker)
    finally:
        _cleanup(kubernetes_client)


# TODO: Next kubernetes python API release might allow multiple object creation for a
# single file (https://github.com/kubernetes-client/python/pull/673). Until it is a
# stable release we invoke `kubectl` directly.`
def _create_deployments(file_path: str) -> typing.Tuple[int, str, str]:
    cmd = "kubectl create -f {}".format(file_path)
    if LOCAL:
        cmd = "eval $(minikube docker-env) && " + cmd
    return _run_kubectl_command(cmd)


def _set_context_namespace(namespace: str) -> typing.Tuple[int, str, str]:
    cmd = "kubectl config set-context $(kubectl config current-context) --namespace={}"
    return _run_kubectl_command(cmd.format(namespace))


def _run_kubectl_command(command: str) -> typing.Tuple[int, str, str]:
    result = subprocess.run(
        [command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
    )

    def parse_output(output) -> str:
        if not output:
            return ""
        return output.decode("utf-8").strip()

    stdout = parse_output(result.stdout)
    stderr = parse_output(result.stderr)
    log.info("Command: %s, Stdout: %s, Stderr: %s", command, stdout, stderr)
    return result.returncode, stdout, stderr


def _cleanup(k_client: client.AppsV1Api) -> None:
    body = client.V1DeleteOptions()
    methods = [
        k_client.delete_namespaced_deployment,
        k_client.delete_namespaced_stateful_set,
    ]
    for name in POD_NAMES:
        for method in methods:
            try:
                method(name, NAMESPACE, body),
            except client.rest.ApiException as e:
                log.info(e)
                if "not found" in e.body:
                    continue
                raise e
