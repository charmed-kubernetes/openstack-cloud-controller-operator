# openstack-cloud-controller

## Description

This charmed operator manages the Cloud Controller component of the OpenStack
Cloud Provider.

## Usage

The charm requires openstack credentials and connection information, which
can be provided via the `openstack-integration` relation to the 
[Openstack Integrator charm](https://charmhub.io/openstack-integrator).


## Deployment

### The full process

```bash
juju deploy charmed-kubernetes
juju config kubernetes-control-plane allow-privileged=true
juju deploy openstack-integrator --trust
juju deploy openstack-cloud-controller
```

You must also tell the cluster on which it is deployed that it will be
acting as an external cloud provider. For Charmed Kubernetes, you can
simply relate it to the control plane.

```bash
juju relate openstack-cloud-controller:certificates  easyrsa:client
juju relate openstack-cloud-controller:kube-control  kubernetes-control-plane:kube-control
juju relate openstack-cloud-controller:openstack     openstack-integrator:clients
juju relate openstack-cloud-controller:external-cloud-provider  kubernetes-control-plane:external-cloud-provider
```

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/charmed-kubernetes/openstack-cloud-controller-operator/blob/main/CONTRIBUTING.md)
for developer guidance.
