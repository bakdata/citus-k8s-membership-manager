import typing
import logging
import hashlib
import time


from threading import Thread
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
        self.masters = masters

    @staticmethod
    def load_config_map(config_path: str) -> typing.List[str]:
        def read_config(path: str) -> typing.List["str"]:
            with open(path, "r") as f:
                return f.readlines()

        return read_config(config_path)

    def update_masters(self):
        log.info("Update masters with new config")
        for pod in self.masters:
            self.provision_master(pod)

    def update_workers(self):
        log.info("Update workers with new config")
        for pod in self.workers:
            self.provision_worker(pod)

    def provision_master(self, pod_name: str) -> None:
        master_provision = self.load_config_map(self.master_provision_path)
        self.provision_node(master_provision, pod_name, self.master_service)

    def provision_worker(self, pod_name: str) -> None:
        worker_provision = self.load_config_map(self.worker_provision_path)
        self.provision_node(worker_provision, pod_name, self.worker_service)

    def provision_node(
        self, queries: typing.List[str], pod_name: str, service_name: str
    ) -> None:
        for query in queries:
            try:
                log.info("Running provision query on: %s", pod_name)
                self.db_handler.execute_query(pod_name, service_name, query)
            except Exception as e:
                log.error("Error %s while executing provision query: %s", e, query)

    def start_watchers(self):
        FileWatcher(self.update_workers, self.master_provision_path).start()
        FileWatcher(self.update_masters, self.worker_provision_path).start()


class FileWatcher:
    def __init__(self, updater: typing.Callable[[], None], file_path: str) -> None:
        self.file_path = file_path
        self.current_hash = self.get_file_hash(self.file_path)
        self.updater = updater

    def start(self) -> None:
        log.info("Start watcher for: %s", self.file_path)

        def run():
            while True:
                new_hash = self.get_file_hash(self.file_path)
                if new_hash != self.current_hash:
                    log.info(
                        "File %s has changed starting provisioning", self.file_path
                    )
                    self.current_hash = new_hash
                    self.updater()
                else:
                    log.info("No changes for %s", self.file_path)
                time.sleep(5)

        Thread(target=run).start()

    @staticmethod
    def get_file_hash(path: str) -> bytes:
        hasher = hashlib.md5()
        with open(path, "rb") as f:
            hasher.update(f.read())
        return hasher.digest()
