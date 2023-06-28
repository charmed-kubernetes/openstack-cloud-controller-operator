# openstack-cloud-controller-operator

## Description

This charmed operator manages the Cloud Controller component of the OpenStack
Cloud Provider.

## Usage

The charm requires OpenStack credentials and connection information, which
can be provided either directly, via config, or via the `openstack-integration`
relation to the [OpenStack Integrator charm](https://charmhub.io/openstack-integrator).

```
juju offer cluster-model.openstack-integrator:clients
juju consume cluster-model.openstack-integrator
juju deploy openstack-cloud-controller-operator
juju relate openstack-cloud-controller-operator openstack-integrator
```

You must also tell the cluster on which it is deployed that it will be
acting as an external cloud provider. For Charmed Kubernetes, you can
simply relate it to the control plane.

```
juju offer openstack-cloud-controller-operator:external-cloud-provider
juju switch cluster-model
juju consume k8s-model.openstack-cloud-controller-operator
juju relate kubernetes-control-plane openstack-cloud-controller-operator
```

For MicroK8s, you will need to manually modified the config for the following
services to set `cloud-provider=external`, as described in the MicroK8s
documentation under [Configuring Services](https://microk8s.io/docs/configuring-services):

  * `snap.microk8s.daemon-apiserver`
  * `snap.microk8s.daemon-controller-manager`
  * `snap.microk8s.daemon-kubelet`

## Relations

In addition to the integration and external cloud provider relations, this
charm provides a `cloud-config` relation for use with charms such as the
Cinder CSI Operator. This relation allows the other charms to be informed
when the `cloud-config` secret is created or updated based on the auth and
connection information provided to this charm.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/openstack-cloud-controller-operator/blob/main/CONTRIBUTING.md)
for developer guidance.
