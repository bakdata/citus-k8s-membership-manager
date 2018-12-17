import os
import logging

from dataclasses import dataclass

log = logging.getLogger(__file__)


@dataclass
class EnvConf:
    namespace: str
    master_label: str
    master_service: str
    worker_label: str
    worker_service: str
    pg_db: str
    pg_user: str
    pg_password: str
    pg_port: int
    master_provision_file: str
    worker_provision_file: str
    minimum_workers: int


def parse_env_vars() -> EnvConf:
    env = os.environ
    conf = EnvConf(
        env["NAMESPACE"],
        env.get("MASTER_LABEL", "citus-master"),
        env.get("MASTER_SERVICE", "pg-citus-master"),
        env.get("WORKER_LABEL", "citus-worker"),
        env.get("WORKER_SERVICE", "pg-citus-worker"),
        env.get("PG_DB", "postgres"),
        env.get("PG_USER", "postgres"),
        env.get("PG_PASSWORD", ""),
        int(env.get("PG_PORT", 5432)),
        env.get("MASTER_PROVISION_FILE", "/etc/config/master.setup"),
        env.get("WORKER_PROVISION_FILE", "/etc/config/worker.setup"),
        int(env.get("MINIMUM_WORKERS", 0)),
    )
    log.info("Environment Config: %s", conf)
    return conf
