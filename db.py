import typing
import psycopg2
import retrying
import logging

from env_conf import EnvConf
from contextlib import contextmanager

log = logging.getLogger(__file__)


class DBHandler:
    def __init__(self, conf: EnvConf) -> None:
        self.pg_params = self.get_pg_connection_parameters(conf)
        self.namespace = conf.namespace
        self.short_url = conf.short_url

    @staticmethod
    def get_pg_connection_parameters(conf: EnvConf) -> dict:
        parameters = {
            "dbname": conf.pg_db,
            "user": conf.pg_user,
            "password": conf.pg_password,
        }
        if not parameters["password"]:
            parameters.pop("password")
        return parameters

    @contextmanager
    def _connect_to_db(
        self, host: str
    ) -> typing.Iterator[psycopg2._psycopg.connection]:
        @retrying.retry(wait_fixed=5 * 1000, stop_max_attempt_number=10)
        def connector() -> psycopg2._psycopg.connection:
            conn = psycopg2.connect(**self.pg_params, host=host)
            return conn

        try:
            connection = connector()
            log.info("Connected to pg db on: %s", host)
            yield connection
        finally:
            connection.commit()
            connection.close()

    def get_host_name(self, pod_name: str, service_name: str) -> str:
        if self.short_url:
            host_pattern = "{pod_name}.{service_name}"
            return host_pattern.format(pod_name=pod_name, service_name=service_name)
        host_pattern = "{pod_name}.{service_name}.{namespace}.svc.cluster.local"
        return host_pattern.format(
            pod_name=pod_name, namespace=self.namespace, service_name=service_name
        )

    def execute_query(
        self, pod_name: str, service_name: str, query: str, query_params: dict = {}
    ) -> None:
        host = self.get_host_name(pod_name, service_name)
        with self._connect_to_db(host) as conn:
            with conn.cursor() as cur:
                log.info("Executing query %s with %s", query, query_params)
                cur.execute(query, query_params)
