import typing
import logging

from env_conf import EnvConf
from db import DBHandler

log = logging.getLogger(__file__)


class ConfigMonitor:
    def __init__(
        self,
        conf: EnvConf,
        db_handler: DBHandler,
        workers: typing.Set[str],
        masters: typing.Set[str],
    ) -> None:
        self.master_provision_path = conf.master_provision_file
        self.worker_provision_path = conf.worker_provision_file
        self.master_service = conf.master_service
        self.worker_service = conf.worker_service
        self.db_handler = db_handler

        self.workers = workers
        self.master = masters

        self.master_provision, self.worker_provision = self.load_config_maps()

    def load_config_maps(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        def read_config(path: str) -> typing.List["str"]:
            with open(path, "r") as f:
                return f.readlines()

        return (
            read_config(self.master_provision_path),
            read_config(self.worker_provision_path),
        )

    def provision_master(self, pod_name: str) -> None:
        self.provision_node(self.master_provision, pod_name, self.master_service)

    def provision_worker(self, pod_name: str) -> None:
        self.provision_node(self.worker_provision, pod_name, self.worker_service)

    def provision_node(
        self, queries: typing.List[str], pod_name: str, service_name: str
    ) -> None:
        for query in queries:
            try:
                log.info("Running provision query on: %s", pod_name)
                self.db_handler.execute_query(pod_name, service_name, query)
            except Exception as e:
                log.error("Error %s while executing provision query: %s", e, query)
