import sys
import logging
import typing
import pytest
import os
import subprocess
import time
import yaml

from kubernetes import config, client
from threading import Thread
from config import (
    NAMESPACE,
    POD_NAMES,
    YAML_DIR,
    MANAGER_DEPLOYMENT,
    SERVICE_ACCOUNT,
    MANAGER_NAME,
    CONFIG_MAP,
    CONFIG_PATH,
    CONFIG_VOLUME,
)

VM_DRIVER = os.environ.get("DRIVER", None)

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
def config_map(namespace):
    core_api = client.CoreV1Api()
    try:
        log.info("Create config map")
        path = YAML_DIR + "provision-map.yaml"
        provision_conf = _parse_single_kubernetes_yaml(path)
        yield core_api.create_namespaced_config_map(NAMESPACE, provision_conf)
    finally:
        log.info("Delete config map")
        body = client.V1DeleteOptions()
        core_api.delete_namespaced_config_map(CONFIG_MAP, NAMESPACE, body)


@pytest.fixture(scope="session")
def manager_service_account(kubernetes_client, namespace):
    try:
        path = YAML_DIR + "pods-list-role-binding.yaml"

        def create_role_binding() -> None:
            cmd = "kubectl apply -f {}".format(path)
            _run_kubectl_command(cmd)

        yield create_role_binding()
    finally:
        body = client.V1DeleteOptions()
        client.CoreV1Api().delete_namespaced_service_account(
            SERVICE_ACCOUNT, NAMESPACE, body
        )
        client.RbacAuthorizationV1Api().delete_cluster_role("pods-list", body)
        client.RbacAuthorizationV1Api().delete_cluster_role_binding("pods-list", body)


@pytest.fixture(scope="session")
def kubernetes_client():
    config.load_kube_config()
    return client.AppsV1Api()


@pytest.fixture(scope="session", autouse=True)
def setup_cluster(kubernetes_client, manager_service_account, config_map):
    try:
        manager_conf = _parse_single_kubernetes_yaml(MANAGER_DEPLOYMENT)
        _configure_manager_pod_template(manager_conf)
        log.info("Manager template: %s", manager_conf)
        kubernetes_client.create_namespaced_deployment(NAMESPACE, manager_conf)
        _capture_manager_output()

        citus_worker = YAML_DIR + "citus-worker.yaml"
        _create_deployments(citus_worker)

        citus_master = YAML_DIR + "citus-master.yaml"
        yield _create_deployments(citus_master)
    finally:
        _cleanup(kubernetes_client)


def _configure_manager_pod_template(manager_conf: dict) -> None:
    template = manager_conf["spec"]["template"]["spec"]
    template["serviceAccountName"] = SERVICE_ACCOUNT

    template["containers"][0]["imagePullPolicy"] = "Never"
    template["containers"][0]["image"] = MANAGER_NAME
    template["containers"][0]["env"] = []
    template["containers"][0]["env"].append({"name": "NAMESPACE", "value": NAMESPACE})
    template["containers"][0]["env"].append({"name": "MINIMUM_WORKERS", "value": "2"})
    template["containers"][0]["env"].append({"name": "SHORT_URL", "value": "True"})

    template["containers"][0]["volumeMounts"][0]["name"] = CONFIG_VOLUME
    template["containers"][0]["volumeMounts"][0]["mountPath"] = CONFIG_PATH

    template["volumes"][0]["name"] = CONFIG_VOLUME
    template["volumes"][0]["configMap"]["name"] = CONFIG_MAP

    manager_conf["spec"]["template"]["spec"] = template


# TODO: Next kubernetes python API release might allow multiple object creation for a
# single file (https://github.com/kubernetes-client/python/pull/673). Until it is a
# stable release we invoke `kubectl` directly.`
def _create_deployments(file_path: str) -> typing.Tuple[int, str, str]:
    cmd = "kubectl create -f {}".format(file_path)
    if VM_DRIVER:
        cmd = "eval $(minikube docker-env) && " + cmd
    return _run_kubectl_command(cmd)


def _capture_manager_output() -> None:
    cmd = "kubectl logs -lapp=citus-manager --tail 5"

    def run():
        while True:
            _run_kubectl_command(cmd)
            time.sleep(3)

    th = Thread(target=run)
    th.daemon = True
    th.start()


def _parse_single_kubernetes_yaml(file_path: str) -> dict:
    with open(file_path, "r") as f:
        return yaml.load(f)


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
