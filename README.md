# citus-k8s-membership-manager

## Manager Pod Environment Config

```python
    env["NAMESPACE"], # Namespace where the manager runs and the citus cluster is supposed to be
    env.get("MASTER_LABEL", "citus-master"), # Label of the citus master pods
    env.get("MASTER_SERVICE", "pg-citus-master"), # Service of the citus master pods
    env.get("WORKER_LABEL", "citus-worker"), # Label of the citus worker pods
    env.get("WORKER_SERVICE", "pg-citus-worker"), # Service of the citus master pods
    env.get("PG_DB", "postgres"), # Database name for master node postgres
    env.get("PG_USER", "postgres"), # Database user for master node postgres
    int(env.get("PG_PORT", 5432)), # Database port for master node postgres
    env.get("LOG_FILE", "manager.log"), # Log file name created in pod
```
