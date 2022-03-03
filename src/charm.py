#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Dispatch logic for the OCC operator charm."""

import json
import logging
from hashlib import md5
from pathlib import Path

from charms.openstack_cloud_controller_operator.v0.cloud_config import (
    CloudConfigProvides,
)
from charms.openstack_cloud_controller_operator.v0.openstack_integration import (
    OpenStackIntegrationRequires,
)
from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from backend import OCCCharmBackend

log = logging.getLogger(__name__)


class OpenStackCloudControllerCharm(CharmBase):
    """Dispatch logic for the OCC operator charm."""

    stored = StoredState()
    version = Path("upstream/version").read_text()

    def __init__(self, *args):
        super().__init__(*args)
        self.stored.set_default(config_hash=None, deployed=False)

        self.backend = OCCCharmBackend(self)
        self.integrator = OpenStackIntegrationRequires(self)
        self.cc_provides = CloudConfigProvides(self)

        self.framework.observe(self.on.config_changed, self._check_config)
        self.framework.observe(self.on.openstack_integration_relation_created, self._check_config)
        self.framework.observe(self.on.openstack_integration_relation_joined, self._check_config)
        self.framework.observe(self.on.openstack_integration_relation_changed, self._check_config)
        self.framework.observe(self.on.openstack_integration_relation_broken, self._check_config)
        self.framework.observe(self.on.install, self._install_or_upgrade)
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.cc_provides.on.available, self._notify_cloud_config)
        self.framework.observe(self.on.leader_elected, self._set_version)
        self.framework.observe(self.on.stop, self._cleanup)

    def _check_config(self, event=None):
        self.unit.status = MaintenanceStatus("Updating cloud-config")
        cloud_config = self.backend.build_cloud_config()
        if not cloud_config["Global"]:
            had_hash = self.stored.config_hash is not None
            self.stored.config_hash = None
            if had_hash:
                self._notify_cloud_config()
            no_relation = not self.integrator.relation
            broken_relation = (
                isinstance(event, RelationBrokenEvent)
                and event.relation is self.integrator.relation
            )
            if no_relation or broken_relation:
                self.unit.status = BlockedStatus("Missing required config or integrator")
            else:
                self.unit.status = WaitingStatus("Waiting for integrator")
            return
        if err := self.backend.validate_cloud_config(cloud_config):
            self.unit.status = BlockedStatus(f"Invalid config: {err}")
            return
        new_hash = md5(json.dumps(cloud_config, sort_keys=True).encode("utf8")).hexdigest()
        if new_hash == self.stored.config_hash:
            # No change
            self.unit.status = ActiveStatus()
            return
        self.stored.config_hash = new_hash
        self.backend.apply_cloud_config(cloud_config)
        if not self.stored.deployed:
            self._install_or_upgrade()
        else:
            self.backend.restart()
            self._notify_cloud_config()
            self.unit.status = ActiveStatus()

    def _install_or_upgrade(self, event=None):
        if not self.stored.config_hash:
            return
        self.unit.status = MaintenanceStatus("Deploying OpenStack Cloud Controller")
        self.backend.apply()
        self.stored.deployed = True
        self.unit.status = ActiveStatus()
        self._set_version()
        self._notify_cloud_config(event)

    def _set_version(self, event=None):
        if self.unit.is_leader():
            self.unit.set_workload_version(self.version)

    def _notify_cloud_config(self, event=None):
        if not self.unit.is_leader() or self.stored.config_hash is None:
            return
        if event:
            relations = [event.relation]
        else:
            relations = self.cc_provides.relations
        for relation in relations:
            self.cc_provides.send_hash(self.stored.config_hash)

    def _cleanup(self, event):
        self.unit.status = MaintenanceStatus("Cleaning up OpenStack Cloud Controller")
        self.backend.remove()
        self.unit.status = MaintenanceStatus("Shutting down")


if __name__ == "__main__":
    main(OpenStackCloudControllerCharm)
