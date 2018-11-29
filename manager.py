import typing
import retrying
import json
import psycopg2
import logging

from kubernetes import client, config, watch
from kubernetes.client import V1Pod
from flask import Flask
from threading import Thread
from env_conf import parse_env_vars


conf = parse_env_vars()

citus_master_nodes: typing.Set[str] = set()
citus_worker_nodes: typing.Set[str] = set()

app = Flask(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(conf.log_file_name), logging.StreamHandler()],
)

log = logging.getLogger(__file__)


@app.route("/registered")
def registered_workers():
    return json.dumps(list(citus_worker_nodes))


def loop() -> None:
    log.info("Starting to watch citus db pods in {}".format(conf.namespace))

    config.load_incluster_config()  # or load_kube_config for external debugging
    api = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(api.list_namespaced_pod, conf.namespace):
        event_type = event["type"]
        pod = event["object"]
        citus_type = get_citus_type(pod)
        pod_name = pod.metadata.name
        log.info(
            "New event %s for pod %s with citus type %s",
            event_type,
            pod_name,
            citus_type,
        )
        if not citus_type or event_type == "MODIFIED":
            continue
        if event_type == "ADDED":
            add_pod(pod_name, citus_type)
        else:
            remove_pod(pod_name, citus_type)


def add_pod(pod_name: str, citus_type: str) -> None:
    def master_handle() -> None:
        citus_master_nodes.add(pod_name)
        # TODO: Handle new master registers

    def worker_handle() -> None:
        add_worker(pod_name)

    _handle_citus_types(citus_type, master_handle, worker_handle)


def remove_pod(pod_name: str, citus_type: str) -> None:
    def master_handle() -> None:
        citus_master_nodes.add(pod_name)

    def worker_handle() -> None:
        remove_worker(pod_name)

    _handle_citus_types(citus_type, master_handle, worker_handle)


def _handle_citus_types(
    citus_type: str,
    master_handle: typing.Callable[[], None],
    worker_handle: typing.Callable[[], None],
) -> None:
    if citus_type == conf.master_label:
        master_handle()
    elif citus_type == conf.worker_label:
        worker_handle()
    else:
        log.error("Not recognized citus type %s", citus_type)


def get_citus_type(pod: V1Pod) -> str:
    labels = pod.metadata.labels
    log.info("Retrieved labels: %s", labels)
    if not labels:
        return ""
    return labels.get("citusType", "")


def add_worker(worker_name: str) -> None:
    log.info("Found new worker: {}".format(worker_name))
    citus_worker_nodes.add(worker_name)
    register_worker(worker_name)


def remove_worker(worker_name: str) -> None:
    log.info("Worker terminated: {}".format(worker_name))
    citus_worker_nodes.remove(worker_name)
    unregister_worker(worker_name)


def register_worker(worker_name: str) -> None:
    exec_on_master("SELECT master_add_node(%(host)s, %(port)s)", worker_name)
    log.info("Registered {}".format(worker_name))


def unregister_worker(worker_name: str) -> None:
    exec_on_master(
        """DELETE FROM pg_dist_shard_placement WHERE nodename=%(host)s AND nodeport=%(port)s;
        SELECT master_remove_node(%(host)s, %(port)s)""",
        worker_name,
    )
    log.info("Unregistered: {}".format(worker_name))


def exec_on_master(query: str, worker_name: str) -> None:
    for master in citus_master_nodes:
        with connect_to_master(get_host_name(master, conf.master_service)) as conn:
            with conn.cursor() as cur:
                worker_host = get_host_name(worker_name, conf.worker_service)
                log.info("Registering host: %s", worker_host)
                cur.execute(query, {"host": worker_host, "port": conf.pg_port})
        conn.close()


@retrying.retry(wait_fixed=5 * 1000, stop_max_attempt_number=10)
def connect_to_master(host: str) -> psycopg2._psycopg.connection:
    log.info("Connecting to db master %s", host)
    conn = psycopg2.connect(
        "dbname={} user={} host={}".format(conf.pg_db, conf.pg_user, host)
    )
    return conn


def get_host_name(pod_name: str, service_name: str) -> str:
    host_pattern = "{pod_name}.{service_name}.{namespace}.svc.cluster.local"
    return host_pattern.format(
        pod_name=pod_name, namespace=conf.namespace, service_name=service_name
    )


if __name__ == "__main__":
    Thread(target=app.run).start()
    loop()
