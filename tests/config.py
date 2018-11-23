import os


NAMESPACE = "integration-test"
PG_CONF = {"user": "postgres", "db": "postgres"}
WORKER_NAME = "pg-citus-worker"
MASTER_NAME = "pg-citus-master"
POD_NAMES = [WORKER_NAME, "citus-manager", MASTER_NAME]
YAML_DIR = os.path.dirname(__file__) + "/test_yaml/"
MANAGER_DEPLOYMENT = os.path.dirname(__file__) + "/../manager-deployment.yaml"
