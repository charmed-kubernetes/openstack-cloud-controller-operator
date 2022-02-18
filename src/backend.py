# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Implementation logic for the OCC operator charm."""

import base64
import logging
from pathlib import Path
from random import choices
from string import hexdigits

import jsonschema
import yaml
from charms.openstack_cloud_controller_operator.v0.lightkube_helpers import (
    LightKubeHelpers,
)
from lightkube.models.apps_v1 import DaemonSet
from lightkube.resources.core_v1 import Secret
from ops.framework import Object

log = logging.getLogger(__name__)


class OCCCharmBackend(Object):
    """Implementation logic for the OCC operator charm."""

    manifests = Path("upstream", "manifests")
    config_schema = yaml.safe_load(Path("schemas", "config-schema.yaml").read_text())

    def __init__(self, charm):
        super().__init__(charm, "backend")
        self.charm = charm
        self.lk_helpers = LightKubeHelpers(charm)

    @property
    def integrator(self):
        """Shortcut to `self.charm.integrator`."""
        return self.charm.integrator

    @property
    def config(self):
        """Shortcut to `self.charm.config`."""
        return self.charm.config

    @property
    def app(self):
        """Shortcut to `self.charm.app`."""
        return self.charm.app

    def apply(self):
        """Apply all of the upstream manifests."""
        for manifest in self.manifests.glob("**/*.yaml"):
            if "secret" in manifest.name:
                # The upstream secret contains dummy data, so skip it.
                continue
            self.lk_helpers.apply_manifest(manifest)

    def restart(self):
        """Restart the OCCM DaemonSet."""
        daemonsets = self.lk_helpers.client.list(
            DaemonSet,
            namespace="kube-system",
            labels={"app.juju.is/created-by": f"{self.app.name}"},
            fields={"metadata.name": "openstack-cloud-controller-manager"},
        )
        if not daemonsets:
            log.error("CCM pod not found to restart")
            return
        ds = daemonsets[0]
        # No "rollout restart" command available, so we patch the DS with
        # an annotation w/ a random value to force a restart.
        ds.metadata.annotations["restart"] = "".join(choices(hexdigits, k=4))
        self.lk_helpers.client.patch(DaemonSet, "openstack-cloud-controller-manager", ds)

    def remove(self):
        """Remove all of the components from the upstream manifests."""
        for manifest in self.manifests.glob("**/*.yaml"):
            self.lk_helpers.delete_manifest(manifest, ignore_unauthorized=True)

    def build_cloud_config(self):
        """Build a set of cloud config params based on config and relation data."""
        section_fields = {
            section_name: list(section["properties"].keys())
            for section_name, section in self.config_schema["properties"].items()
        }
        cloud_config = {
            "Global": {
                "auth-url": self.integrator.auth_url,
                "region": self.integrator.region,
                "username": self.integrator.username,
                "password": self.integrator.password,
                "domain-name": self.integrator.user_domain_name,
                "tenant-domain-name": self.integrator.project_domain_name,
                "tenant-name": self.integrator.project_name,
                "subnet-id": self.integrator.subnet_id,
                "floating-network-id": self.integrator.floating_network_id,
                "lb-method": self.integrator.lb_method,
                # Charm config overrides relation data.
                **{k: self.config[k] for k in section_fields["Global"] if self.config.get(k)},
            },
            "LoadBalancer": {k: self.config.get(k) for k in section_fields["LoadBalancer"]},
        }
        # Clear out empty / null values.
        for section in cloud_config.values():
            for key in list(section.keys()):
                if section[key] == "" or section[key] is None:
                    del section[key]
        return cloud_config

    def validate_cloud_config(self, cloud_config):
        """Validate the given cloud config params and return any error."""
        try:
            jsonschema.validate(cloud_config, self.config_schema)
        except jsonschema.ValidationError as e:
            log.exception("Failed to validate cloud config params")
            return e.message
        return None

    def apply_cloud_config(self, cloud_config):
        """Create or update the `cloud-config` Secret resource."""
        cloud_conf = []
        for section_name, section in cloud_config.items():
            if not section:
                continue
            cloud_conf.append(f"[{section_name}]")
            cloud_conf.extend("{key}={value}" for key, value in section.items())
            cloud_conf.append("")
        cloud_conf = ("\n".join(cloud_conf) + "\n").encode("utf8")
        self.lk_helpers.apply_resource(
            Secret,
            name="cloud-config",
            namespace="kube-system",
            data={"cloud.conf": base64.encodebytes(cloud_conf).decode("utf8")},
        )

    def delete_cloud_config(self):
        """Remove the `cloud-config` Secret resource, if we created it."""
        secrets = self.lk_helpers.client.list(
            Secret,
            namespace="kube-control",
            labels={"app.juju.is/created-by": f"{self.app.name}"},
            fields={"metadata.name": "cloud-config"},
        )
        if not secrets:
            return
        self.lk_helpers.delete_resource(
            Secret,
            name="cloud-config",
            namespace="kube-system",
        )
