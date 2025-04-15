# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest.mock as mock

import pytest
from lightkube.models.core_v1 import Container, EnvVar, Volume
from lightkube.resources.apps_v1 import DaemonSet

import provider_manifests
from charm import KubeControlRequirer, OpenstackIntegrationRequirer, ProviderCharm
from config import CharmConfig

CLUSTER_NAME = "k8s-cluster-name"
PROXY_URL = "http://proxy:80"
PROXY_URL_1 = f"{PROXY_URL}81"
PROXY_URL_2 = f"{PROXY_URL}82"
NO_PROXY = "127.0.0.1,localhost,::1"


@pytest.fixture
def charm_config():
    """Return the charm config."""
    config = mock.MagicMock(spec=CharmConfig)
    config.available_data = {
        "cloud-conf": b"abc",
        "endpoint-ca-cert": b"def",
    }
    return config


@pytest.fixture
def kube_control():
    """Return the kube control mock."""
    kube_control = mock.MagicMock(spec=KubeControlRequirer)
    kube_control.evaluate_relation.return_value = None
    kube_control.kubeconfig = b"abc"
    kube_control.get_cluster_tag.return_value = CLUSTER_NAME
    return kube_control


@pytest.fixture
def integrator():
    """Return the openstack integration mock."""
    integrator = mock.MagicMock(spec=OpenstackIntegrationRequirer)
    integrator.evaluate_relation.return_value = None
    integrator.cloud_conf_b64 = b"abc"
    integrator.endpoint_tls_ca = b"def"
    integrator.proxy_config = {
        "HTTP_PROXY": PROXY_URL_1,
        "HTTPS_PROXY": PROXY_URL_2,
        "NO_PROXY": NO_PROXY,
    }
    return integrator


@pytest.fixture
def provider(kube_control, charm_config, integrator):
    """Return the manifests object."""
    yield provider_manifests.ProviderManifests(
        mock.MagicMock(spec=ProviderCharm),
        charm_config,
        kube_control,
        integrator,
    )


def test_patch_daemon_set(provider):
    """Test the patching of the daemon set."""

    update_ds = provider.manipulations[-1]
    assert isinstance(update_ds, provider_manifests.UpdateDaemonSet)

    secret_volume = mock.MagicMock(spec=Volume)
    cluster_env = EnvVar(name="CLUSTER_NAME", value="set-me")

    container = mock.MagicMock(spec=Container)
    container.env = [cluster_env]

    ds = mock.MagicMock(spec=DaemonSet)
    ds.kind = "DaemonSet"
    container.name = ds.metadata.name = "openstack-cloud-controller-manager"
    ds.spec.template.spec.volumes = [secret_volume]
    ds.spec.template.spec.containers = [container]

    update_ds(ds)
    assert secret_volume.secret.secretName == "cloud-controller-config"
    assert EnvVar(name="CLUSTER_NAME", value=CLUSTER_NAME) in container.env
    assert EnvVar(name="HTTP_PROXY", value=PROXY_URL_1) in container.env
    assert EnvVar(name="HTTPS_PROXY", value=PROXY_URL_2) in container.env
    assert EnvVar(name="NO_PROXY", value=NO_PROXY) in container.env
