# citus-k8s-membership-manager

This project implements the citus membership-manager for kubernetes. Currently, the membership-manager monitors the pods in the current namespace and registers or unregisters worker pods at the master node when they are added or removed.

## Setup

First, it is recommended to create a dedicated namespace for the membership-member or if your citus cluster is already running you can reuse this namespace. Furthermore, you have to create a service account allowing the membership-manager to list all pods in the current namespace.
Once you have created the service account and have a namespace the following role and role binding need to be created:

```yaml

kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: pods-list
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "watch", "list"]
---
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: pods-list
subjects:
- kind: ServiceAccount
  name: <your-service-account-name>
  namespace: <your-namespace>
roleRef:
  kind: ClusterRole
  name: pods-list
  apiGroup: rbac.authorization.k8s.io

```

If you want to do the same on Google's Kubernetes Engine you might have to create a cluster admin binding first which sets your current google user as cluster admin

```shell
kubectl create clusterrolebinding <your--binding-name> --clusterrole=cluster-admin --user=<email-address-used-for-this-google-account>
```

## Manager Pod Environment Config

The following environment variables are configurable on pod startup. Hereby the second parameter is automatically used as default if none is provided.

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

## Development

Since the main development for this tool is done in Python we decided to use [black](https://github.com/ambv/black) as formatting tool and [mypy](http://mypy-lang.org/) as type hinting tool. If you want to contribute please install these tools in your favorite IDE or use them as cli tools to keep the code consistent. When you want to make your first changes you can install the needed dependencies with running the following commands in the root directory of the repository.

```shell
pipenv install --dev
pipenv shell
```

To run the tests locally you first have to install [minikube](https://kubernetes.io/docs/setup/minikube/) on your machine. We have tested the following cluster configuration:

```shell
minikube start --memory 4096 --cpus 4 --vm-driver hyperkit --bootstrapper=kubeadm
```

Afterward, you can run `pytest`.
