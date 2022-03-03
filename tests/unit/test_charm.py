# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
from unittest.mock import Mock

import pytest
from charms.openstack_cloud_controller_operator.v0.cloud_config import (
    MockCloudConfigRequires,
)
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import OpenStackCloudControllerCharm


@pytest.fixture
def harness():
    harness = Harness(OpenStackCloudControllerCharm)
    try:
        yield harness
    finally:
        harness.cleanup()


@pytest.fixture
def lk_client(monkeypatch):
    monkeypatch.setattr(
        "charms.openstack_cloud_controller_operator.v0.lightkube_helpers.Client",
        client := Mock(name="lightkube.Client"),
    )
    return client


def test_ccm(harness, lk_client):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.charm.unit.status, BlockedStatus)

    # Remove caching from properties (happens automatically for the
    # cloud-config relation provider).
    rel_cls = type(harness.charm.integrator)
    del harness.charm.integrator.relation
    rel_cls.relation = property(rel_cls.relation.func)
    del harness.charm.integrator._data
    rel_cls._data = property(rel_cls._data.func)

    rel_id = harness.add_relation("openstack-integration", "integrator")
    assert isinstance(harness.charm.unit.status, WaitingStatus)
    harness.add_relation_unit(rel_id, "integrator/0")
    assert isinstance(harness.charm.unit.status, WaitingStatus)
    harness.update_relation_data(
        rel_id,
        "integrator/0",
        {
            "auth_url": json.dumps("auth_url"),
            "region": json.dumps("region"),
            "username": json.dumps("username"),
            "password": json.dumps("password"),
            "user_domain_name": json.dumps("user_domain_name"),
            "project_domain_name": json.dumps("project_domain_name"),
            "project_name": json.dumps("project_name"),
        },
    )
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    harness.remove_relation(rel_id)
    assert isinstance(harness.charm.unit.status, BlockedStatus)

    lk_client().list.return_value = [Mock(**{"metadata.annotations": {}})]
    harness.update_config(
        {
            "auth-url": "http://example.com/v3",
            "region": "east",
            "application-credential-id": "cred-id",
            "application-credential-secret": "cred-secret",
        }
    )
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    cc_requires = MockCloudConfigRequires(harness)
    cc_requires.relate()
    assert cc_requires.config_hash
