# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest.mock as mock
from pathlib import Path

import pytest
import yaml
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import ProviderCharm


@pytest.fixture
def harness():
    harness = Harness(ProviderCharm)
    harness.disable_hooks()
    harness.begin()
    try:
        yield harness
    finally:
        harness.cleanup()


@pytest.fixture(autouse=True)
def mock_kubeconfig(tmpdir):
    kubeconfig = Path(tmpdir) / "kubeconfig"
    with mock.patch.object(
        ProviderCharm, "_kubeconfig_path", new_callable=mock.PropertyMock(return_value=kubeconfig)
    ):
        yield kubeconfig


@pytest.fixture(autouse=True)
def mock_ca_cert(tmpdir):
    ca_cert = Path(tmpdir) / "ca.crt"
    with mock.patch.object(
        ProviderCharm, "_ca_cert_path", new_callable=mock.PropertyMock(return_value=ca_cert)
    ):
        yield ca_cert


@pytest.fixture()
def valid_cloud_config_data():
    return Path("tests/data/resources/cloud.conf").read_text()


@pytest.fixture()
def invalid_cloud_config_data():
    return Path("tests/data/resources/invalid.conf").read_text()


@pytest.fixture()
def integrator_data():
    return yaml.safe_load(Path("tests/data/openstack_data.yaml").read_text())


@pytest.fixture()
def integrator(harness, integrator_data):
    with harness.hooks_disabled():
        rel_id = harness.add_relation("openstack", "openstack-integrator")
        harness.add_relation_unit(rel_id, "openstack-integrator/0")
        harness.update_relation_data(rel_id, "openstack-integrator/0", integrator_data)
    yield harness.charm.integrator


@pytest.fixture()
def certificates_data():
    return yaml.safe_load(Path("tests/data/certificates_data.yaml").read_text())


@pytest.fixture()
def certificates(harness, certificates_data):
    with harness.hooks_disabled():
        rel_id = harness.add_relation("certificates", "easyrsa")
        harness.add_relation_unit(rel_id, "easyrsa/0")
        harness.update_relation_data(rel_id, "easyrsa/0", certificates_data)
    yield harness.charm.certificates


@pytest.fixture()
def kube_control_data():
    return yaml.safe_load(Path("tests/data/kube_control_data.yaml").read_text())


@pytest.fixture()
def kube_control(harness, kube_control_data):
    with harness.hooks_disabled():
        rel_id = harness.add_relation("kube-control", "k8s")
        harness.add_relation_unit(rel_id, "k8s/0")
        harness.update_relation_data(rel_id, "k8s/0", kube_control_data)
    yield harness.charm.kube_control


def test_waits_for_integrator(harness, integrator_data):
    charm = harness.charm
    harness.enable_hooks()

    # Test adding the integrator relation
    rel_cls = type(charm.integrator)
    rel_cls.relation = property(rel_cls.relation.func)
    rel_cls._data = property(rel_cls._data.func)
    rel_cls._raw_data = property(rel_cls._raw_data.func)
    rel_id = harness.add_relation("openstack", "openstack-integrator")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for openstack"
    harness.add_relation_unit(rel_id, "openstack-integrator/0")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for openstack"
    harness.update_relation_data(rel_id, "openstack-integrator/0", integrator_data)
    assert isinstance(charm.unit.status, BlockedStatus)
    assert charm.unit.status.message == "Missing required certificates"


@pytest.mark.usefixtures("integrator")
def test_waits_for_certificates(harness, certificates_data):
    charm = harness.charm
    harness.enable_hooks()

    # Test adding the certificates relation
    rel_cls = type(charm.certificates)
    rel_cls.relation = property(rel_cls.relation.func)
    rel_cls._data = property(rel_cls._data.func)
    rel_cls._raw_data = property(rel_cls._raw_data.func)
    rel_id = harness.add_relation("certificates", "easyrsa")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for certificates"
    harness.add_relation_unit(rel_id, "easyrsa/0")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for certificates"
    harness.update_relation_data(rel_id, "easyrsa/0", certificates_data)
    assert isinstance(charm.unit.status, BlockedStatus)
    assert charm.unit.status.message == "Missing required kube-control relation"


@mock.patch("ops.interface_kube_control.KubeControlRequirer.create_kubeconfig")
@pytest.mark.usefixtures("integrator", "certificates")
def test_waits_for_kube_control(mock_create_kubeconfig, harness, kube_control_data, caplog):
    charm = harness.charm
    harness.enable_hooks()

    # Add the kube-control relation
    rel_cls = type(charm.kube_control)
    rel_cls.relation = property(rel_cls.relation.func)
    rel_cls._data = property(rel_cls._data.func)
    rel_id = harness.add_relation("kube-control", "k8s")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for kube-control relation"

    harness.add_relation_unit(rel_id, "k8s/0")
    assert isinstance(charm.unit.status, WaitingStatus)
    assert charm.unit.status.message == "Waiting for kube-control relation"
    mock_create_kubeconfig.assert_not_called()

    caplog.clear()

    with mock.patch.object(charm, "_install_or_upgrade") as mock_install:
        harness.update_relation_data(rel_id, "k8s/0", kube_control_data)

    assert isinstance(charm.unit.status, MaintenanceStatus)
    assert charm.unit.status.message == "Evaluating Manifests"
    mock_install.assert_called_once()
    mock_create_kubeconfig.assert_called_once_with(
        charm._ca_cert_path, charm._kubeconfig_path, "root", charm.unit.name
    )


@mock.patch("ops.interface_kube_control.KubeControlRequirer.create_kubeconfig", new=mock.Mock())
@pytest.mark.usefixtures("integrator", "certificates", "kube_control")
def test_install_or_upgrade(harness, caplog):
    charm = harness.charm
    harness.enable_hooks()
    harness.update_config({})
    assert charm.unit.status == MaintenanceStatus("Deploying Cloud Controller Manager")
    storage_messages = {r.message for r in caplog.records if "provider" in r.filename}

    assert storage_messages == {
        "Encode secret data for cloud-controller.",
        "Patching cluster-name for DaemonSet/openstack-cloud-controller-manager by env",
        "Setting hash for DaemonSet/openstack-cloud-controller-manager",
        "Setting secret for DaemonSet/openstack-cloud-controller-manager",
    }

    caplog.clear()


@mock.patch("ops.interface_kube_control.KubeControlRequirer.create_kubeconfig", new=mock.Mock())
@pytest.mark.usefixtures("integrator", "certificates", "kube_control")
def test_overlay_cloud_config(harness, caplog, valid_cloud_config_data):
    charm = harness.charm
    harness.enable_hooks()
    harness.add_resource("cloud-config-overlay", valid_cloud_config_data)
    harness.charm.on.upgrade_charm.emit()
    assert charm.unit.status == MaintenanceStatus("Deploying Cloud Controller Manager")
    storage_messages = {r.message for r in caplog.records if "src/provider" in r.pathname}
    config_messages = {r.message for r in caplog.records if "src/config" in r.pathname}

    assert config_messages == {
        f"Loaded cloud config overlay from resource (size: {len(valid_cloud_config_data)})",
        "Applying cloud-config-overlay from charm resource.",
    }

    assert storage_messages == {
        "Encode secret data for cloud-controller.",
        "Patching cluster-name for DaemonSet/openstack-cloud-controller-manager by env",
        "Setting hash for DaemonSet/openstack-cloud-controller-manager",
        "Setting secret for DaemonSet/openstack-cloud-controller-manager",
    }

    caplog.clear()


@mock.patch("ops.interface_kube_control.KubeControlRequirer.create_kubeconfig", new=mock.Mock())
@pytest.mark.usefixtures("integrator", "certificates", "kube_control")
def test_overlay_cloud_config_invalid(harness, invalid_cloud_config_data):
    charm = harness.charm
    harness.enable_hooks()
    # truncate to make invalid
    harness.add_resource("cloud-config-overlay", invalid_cloud_config_data)
    harness.charm.on.upgrade_charm.emit()
    assert charm.unit.status == BlockedStatus("Invalid cloud-config-overlay")
