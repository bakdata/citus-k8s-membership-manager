# citus-k8s-membership-manager
[![Build Status](https://travis-ci.com/bakdata/citus-k8s-membership-manager.svg?branch=master)](https://travis-ci.com/bakdata/citus-k8s-membership-manager)
[![Code Climate](https://codeclimate.com/github/bakdata/citus-k8s-membership-manager/badges/gpa.svg)](https://codeclimate.com/github/bakdata/citus-k8s-membership-manager)
[![](https://img.shields.io/docker/automated/jrottenberg/ffmpeg.svg)](https://hub.docker.com/r/bakdata/citus-k8s-membership-manager)


This project aims to provide a service which helps running PostgreSQL with the [Citus](https://github.com/citusdata/citus) extension on kubernetes.

Hereby, it supports the following features:

- Register/unregister worker nodes on master during startup/teardown
- Wait until worker threshold is reached before provisioning
- Running provision scripts (SQL) on master/worker node startup

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

### Provisioning

In addition to the service account, you also have to create a ConfigMap to provision worker and master nodes. An example can be found here [tests/test\_yaml/provision-map.yaml](tests/test\_yaml/provision-map.yaml).

**IMPORTANT:** Keep the same file structure with all its keys and only change the two value strings for `master.setup` and `worker.setup`. The membership-manager will check for these file names specifically.

### Labels

- Add `citusType` label to master and worker nodes
```
kubectl patch statefulset  <statefulset-name> -n <namespace> --patch '{"spec": {"template": {"metadata": {"labels": {"citusType": <your-label>}}}}}'
```


### Installation

Finally to deploy the membership-manager with 
```
kubectl create -f manager-deployment.yaml
``` 
you have to edit the yaml file replacing the template variables (`<your-service-account>`, `<your-namespace>`) with the corresponding names in your setup.


### GKE

If you want to do the same on Google's Kubernetes Engine you might have to create a cluster admin binding first which sets your current google user as cluster admin

```shell
kubectl create clusterrolebinding <your--binding-name> --clusterrole=cluster-admin --user=<email-address-used-for-this-google-account>
```

## Manager Pod Environment Config

The following environment variables are configurable on pod startup. Before the deployment you can set those in the `manager-deployment.yaml` file.

```yml
env:
- name: NAMESPACE
  value: <your-namespace> # Namespace where the manager runs and the citus cluster is supposed to be
- name: MASTER_LABEL
  value: <default: citus-master> # Label of the citus master pods
- name: MASTER_SERVICE
  value: <default: pg-citus-master> # Service of the citus master pods
- name: WORKER_LABEL
  value: <default: citus-worker> # Label of the citus worker pods
- name: WORKER_SERVICE
  value: <default: pg-citus-worker> # Service of the citus worker pods
- name: PG_DB
  value: <default: postgres> # Database name for postgres db
- name: PG_USER
  value: <default: postgres> # Database user for postgres db
- name: PG_PORT
  value: <default: 5432> # Database port for postgres db
- name: PG_PASSWORD
  value: <default: None> # If present it is used for all the connections to the pg nodes
- name: MINIMUM_WORKERS
  value: <default: 0> # Threshold until the manager waits with node provisioning
- name: SHORT_URL
  value: <default: False> # If set {pod_name}.{service_name} is used as host pattern instead of {pod_name}.{service_name}.{namespace}.svc.cluster.local
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
