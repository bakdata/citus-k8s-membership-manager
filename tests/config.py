import os


NAMESPACE = "integration-test"
PG_CONF = {"user": "postgres", "db": "postgres"}
WORKER_NAME = "pg-citus-worker"
WORKER_COUNT = 2
MASTER_NAME = "pg-citus-master"
MANAGER_NAME = "citus-manager"
POD_NAMES = [WORKER_NAME, MANAGER_NAME, MASTER_NAME]
YAML_DIR = os.path.dirname(__file__) + "/test_yaml/"
MANAGER_DEPLOYMENT = os.path.dirname(__file__) + "/../manager-deployment.yaml"
SERVICE_ACCOUNT = "pod-listing-sa"
READINESS_WAIT = 20

CONFIG_MAP = "setup-config"
