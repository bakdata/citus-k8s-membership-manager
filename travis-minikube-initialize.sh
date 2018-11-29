#!/usr/bin/env bash

#curl -Lo minikube https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 && chmod +x minikube
#curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && chmod +x kubectl

curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v1.10.0/bin/linux/amd64/kubectl && chmod +x kubectl && sudo mv kubectl /usr/local/bin/
curl -Lo minikube https://storage.googleapis.com/minikube/releases/v0.30.0/minikube-linux-amd64 && chmod +x minikube && sudo mv minikube /usr/local/bin/

export MINIKUBE_WANTUPDATENOTIFICATION=false
export MINIKUBE_WANTREPORTERRORPROMPT=false
export MINIKUBE_HOME=$HOME
export CHANGE_MINIKUBE_NONE_USER=true
mkdir $HOME/.kube &> /dev/null || true
touch $HOME/.kube/config

export KUBECONFIG=$HOME/.kube/config
sudo -E minikube start --vm-driver=none --memory 4096 --cpus 2 --bootstrapper=kubeadm --kubernetes-version=v1.10.0

# this for loop waits until kubectl can access the api server that minikube has created
KUBECTL_UP="false"
for i in {1..150} # timeout for 5 minutes
do
    echo "Waiting for API server"
    kubectl get po &> /dev/null
    if [ $? -ne 1 ]; then
        KUBECTL_UP="true"
        break
    fi
    sleep 2
done
if [ "$KUBECTL_UP" != "true" ]; then
    echo "INIT FAILURE: kubectl could not reach api-server in allotted time"
    exit 1
fi
# kubectl commands are now able to interact with minikube cluster

# OPTIONAL depending on kube-dns requirement
# this for loop waits until the kubernetes addons are active
kubectl create clusterrolebinding add-on-cluster-admin --clusterrole=cluster-admin --serviceaccount=kube-system:default
KUBE_ADDONS_UP="false"
for i in {1..150} # timeout for 5 minutes
do
    echo "Waiting for API server"
    # Here we are making sure that kubectl is returning the addon pods for the namespace kube-system
    # Without this check, the second if statement won't be in the proper state for execution
    if [[ $(kubectl get po -n kube-system -l k8s-app=kube-dns | tail -n +2 | grep "kube-dns") ]]; then
        # Here we are taking the checking the number of running pods for the namespace kube-system
        # and making sure that the value on each side of the '/' is equal (ex: 3/3 pods running)
        # this is necessary to ensure that all addons have come up
        if [[ ! $(kubectl get po -n kube-system | tail -n +2 | awk '{print $2}' | grep -wEv '^([1-9]+)\/\1$') ]]; then
            echo "INIT SUCCESS: all kubernetes addons pods are up and running"
            KUBE_ADDONS_UP="true"
            break
        fi
   fi
  sleep 2
done
if [ "$KUBE_ADDONS_UP" != "true" ]; then
    echo "INIT FAILURE: kubernetes addons did not come up in allotted time"
    exit 1
fi
# kube-addons is available for cluster services
