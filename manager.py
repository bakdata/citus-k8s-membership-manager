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
from db import DBHandler


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()],
)

log = logging.getLogger(__file__)


class Manager:
    def __init__(self) -> None:
        self.conf = parse_env_vars()
        self.db_handler = DBHandler(self.conf)

        self.citus_master_nodes: typing.Set[str] = set()
        self.citus_worker_nodes: typing.Set[str] = set()
        self.start_web_server()
        self.master_provision, self.worker_provision = self.load_config_maps()
        self.pod_interactions: typing.Dict[
            str, typing.Dict[str, typing.Callable[[str], None]]
        ] = {
            "ADDED": {
                self.conf.master_label: self.add_master,
                self.conf.worker_label: self.add_worker,
            },
            "DELETED": {
                self.conf.master_label: self.remove_master,
                self.conf.worker_label: self.remove_worker,
            },
        }

    def load_config_maps(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        def read_config(path: str) -> typing.List["str"]:
            with open(self.conf.master_provision_file, "r") as f:
                return f.readlines()

        return (
            read_config(self.conf.master_provision_file),
            read_config(self.conf.worker_provision_file),
        )

    @staticmethod
    def get_citus_type(pod: V1Pod) -> str:
        labels = pod.metadata.labels
        log.info("Retrieved labels: %s", labels)
        if not labels:
            return ""
        return labels.get("citusType", "")

    def run(self) -> None:
        log.info("Starting to watch citus db pods in {}".format(self.conf.namespace))

        config.load_incluster_config()  # or load_kube_config for external debugging
        api = client.CoreV1Api()
        w = watch.Watch()
        for event in w.stream(api.list_namespaced_pod, self.conf.namespace):
            event_type = event["type"]
            pod = event["object"]
            citus_type = self.get_citus_type(pod)
            pod_name = pod.metadata.name
            log.info(
                "New event %s for pod %s with citus type %s",
                event_type,
                pod_name,
                citus_type,
            )
            if not citus_type or event_type not in self.pod_interactions:
                continue
            handler = self.pod_interactions[event_type]
            if citus_type not in handler:
                log.error("Not recognized citus type %s", citus_type)
            handler[citus_type](pod_name)

    def start_web_server(self) -> None:
        app = Flask(__name__)

        @app.route("/registered")
        def registered_workers() -> str:
            return json.dumps(list(self.citus_worker_nodes))

        Thread(target=app.run).start()

    def provision_node(
        self, queries: typing.List[str], pod_name: str, service_name: str
    ) -> None:
        for query in queries:
            try:
                log.info("Running provision query on: %s", pod_name)
                self.db_handler.execute_query(pod_name, service_name, query)
            except Exception as e:
                log.error("Error %s while executing provision query: %s", e, query)

    def add_master(self, pod_name: str) -> None:
        self.citus_master_nodes.add(pod_name)
        self.provision_node(self.master_provision, pod_name, self.conf.master_service)
        log.info("Registering new master %s", pod_name)
        for worker_pod in self.citus_worker_nodes:
            self.add_worker(worker_pod)

    def remove_master(self, pod_name: str) -> None:
        self.citus_master_nodes.remove(pod_name)

    def add_worker(self, pod_name: str) -> None:
        self.citus_worker_nodes.add(pod_name)
        self.provision_node(self.worker_provision, pod_name, self.conf.worker_service)
        self.exec_on_masters("SELECT master_add_node(%(host)s, %(port)s)", pod_name)
        log.info("Registered worker %s", pod_name)

    def remove_worker(self, worker_name: str) -> None:
        log.info("Worker terminated: %s", worker_name)
        self.citus_worker_nodes.remove(worker_name)
        self.exec_on_masters(
            """DELETE FROM pg_dist_shard_placement WHERE nodename=%(host)s AND nodeport=%(port)s;
            SELECT master_remove_node(%(host)s, %(port)s)""",
            worker_name,
        )
        log.info("Unregistered: %s", worker_name)

    def exec_on_masters(self, query: str, worker_name: str) -> None:
        for master in self.citus_master_nodes:
            worker_host = self.db_handler.get_host_name(
                worker_name, self.conf.worker_service
            )
            query_params = {"host": worker_host, "port": self.conf.pg_port}
            self.db_handler.execute_query(
                master, self.conf.master_service, query, query_params
            )


if __name__ == "__main__":
    manager = Manager()
    manager.run()
