### citus-k8s-membership-manager v0.3 (January 10, 2019) ###
* Decrease setup complexity by reducing configuration overhead
* Allow passing of ssl mode for pg connections
* Wait for pods' exposed readiness before provisioning
* Fix matching nodes with correct provision scripts
* Run tests with latest Citus docker image
* Enable linting checks in Travis CI

### citus-k8s-membership-manager v0.2 (December 21, 2018) ###
* Use smaller docker base image
* Allow for short kubernetes urls in postgres citus master
* Provision nodes with config map
* Listen on config map changes and update nodes accordingly
* Introduce wait counter for initial provisioning
