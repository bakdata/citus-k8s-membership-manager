import os
from dataclasses import dataclass


@dataclass
class EnvConf:
    namespace: str
    master_label: str
    master_service: str
    worker_label: str
    worker_service: str
    pg_db: str
    pg_user: str
    pg_port: int
    log_file_name: str


def parse_env_vars() -> EnvConf:
    env = os.environ
    return EnvConf(
        env.get("NAMESPACE", "cbo"),
        env.get("MASTER_LABEL", "citus-master"),
        env.get("MASTER_SERVICE", "pg-citus-master"),
        env.get("WORKER_LABEL", "citus-worker"),
        env.get("WORKER_SERVICE", "pg-citus-worker"),
        env.get("PG_DB", "postgres"),
        env.get("PG_USER", "postgres"),
        int(env.get("PG_PORT", 5432)),
        env.get("LOG_FILE", "manager.log"),
    )
