### citus-k8s-membership-manager v0.2 (December 21, 2018) ###
* Use smaller docker base image
* Allow for short kubernetes urls in postgres citus master
* Provision nodes with config map
* Listen on config map changes and update nodes accordingly
* Introduce wait counter for initial provisioning
