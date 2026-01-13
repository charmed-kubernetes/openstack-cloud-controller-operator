# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Implementation of cloud-controller specific details of the kubernetes manifests."""

import base64
import hashlib
import json
import logging
from typing import Dict, Optional

import charms.proxylib
from lightkube.codecs import AnyResource, from_dict
from ops.interface_kube_control import KubeControlRequirer
from ops.interface_openstack_integration import OpenstackIntegrationRequirer
from ops.manifests import Addition, ConfigRegistry, ManifestLabel, Manifests, Patch

from config import CharmConfig

log = logging.getLogger(__file__)
NAMESPACE = "kube-system"
RESOURCE_NAME = "openstack-cloud-controller-manager"
SECRET_NAME = "cloud-controller-config"
K8S_DEFAULT_NO_PROXY = ["127.0.0.1", "localhost", "::1", "svc", "svc.cluster", "svc.cluster.local"]


class CreateSecret(Addition):
    """Create secret for the deployment.

    a secret named cloud-config in the kube-system namespace
    cloud.conf -- base64 encoded contents of cloud.conf
    endpoint-ca.cert -- base64 encoded ca cert for the auth-url
    """

    CONFIG_TO_SECRET = {"cloud-conf": "cloud.conf", "endpoint-ca-cert": "endpoint-ca.cert"}

    def __call__(self) -> Optional[AnyResource]:
        """Craft the secrets object for the deployment."""
        secret_config = {}
        for k, new_k in self.CONFIG_TO_SECRET.items():
            if value := self.manifests.config.get(k):
                secret_config[new_k] = value

        log.info("Encode secret data for cloud-controller.")
        return from_dict(
            dict(
                apiVersion="v1",
                kind="Secret",
                type="Opaque",
                metadata=dict(name=SECRET_NAME, namespace=NAMESPACE),
                data=secret_config,
            )
        )


class UpdateDaemonSet(Patch):
    """Update the CCM DaemonSets."""

    def __call__(self, obj: AnyResource):
        """Patch the openstack CCM daemonset."""
        if not (obj.kind == "DaemonSet" and obj.metadata.name == RESOURCE_NAME):
            return

        # Rolling restart when the hash changes
        hash_key = "juju.is/manifest-hash"
        hash_value = str(self.manifests.hash())
        if not (annotations := obj.spec.template.metadata.annotations):
            annotations = obj.spec.template.metadata.annotations = {}
        annotations[hash_key] = hash_value
        log.info("Setting hash for %s/%s", obj.kind, obj.metadata.name)

        for volume in obj.spec.template.spec.volumes:
            if volume.secret:
                volume.secret.secretName = SECRET_NAME
                log.info(f"Setting secret for {obj.kind}/{obj.metadata.name}")

        msg = f"Patching node-selector for {obj.kind}/{obj.metadata.name}"
        if selector := obj.spec.template.spec.nodeSelector:
            selector_value = selector.get("node-role.kubernetes.io/control-plane")
            if selector_value:
                selector["node-role.kubernetes.io/control-plane"] = ""
                log.info(f"{msg} node-role.kubernetes.io/control-plane='' not '{selector_value}'")

        cluster_name = self.manifests.config.get("cluster-name")
        msg = f"Patching cluster-name for {obj.kind}/{obj.metadata.name}"
        for container in obj.spec.template.spec.containers:
            if container.name == RESOURCE_NAME:
                for env in container.env:
                    if env.name == "CLUSTER_NAME":
                        env.value = cluster_name
                        log.info(f"{msg} by env")

                enabled = self.manifests.config.get("web-proxy-enable")
                env = charms.proxylib.environ(enabled=enabled, add_no_proxies=K8S_DEFAULT_NO_PROXY)
                container.env.extend(charms.proxylib.container_vars(env))


class ProviderManifests(Manifests):
    """Deployment Specific details for the cloud-controller-manager."""

    def __init__(
        self,
        charm,
        charm_config: CharmConfig,
        kube_control: KubeControlRequirer,
        integrator: OpenstackIntegrationRequirer,
    ):
        super().__init__(
            RESOURCE_NAME,
            charm.model,
            "upstream/controller_manager",
            [
                CreateSecret(self),
                ManifestLabel(self),
                ConfigRegistry(self),
                UpdateDaemonSet(self),
            ],
        )
        self.integrator = integrator
        self.charm_config = charm_config
        self.kube_control = kube_control

    @property
    def config(self) -> Dict:
        """Returns current config available from charm config and joined relations."""
        base_cloud_conf = ""
        if raw := self.integrator.cloud_conf_b64:
            base_cloud_conf = base64.b64decode(raw).decode()

        merged_cloud_conf = self.charm_config.merged_cloud_conf(base_cloud_conf)
        merged_cloud_conf_b64 = base64.b64encode(merged_cloud_conf.encode()).decode()

        config = {
            "image-registry": self.kube_control.get_registry_location(),
            "cluster-name": self.kube_control.get_cluster_tag(),
            "cloud-conf": merged_cloud_conf_b64,
            "endpoint-ca-cert": (val := self.integrator.endpoint_tls_ca) and val.decode(),
            **self.charm_config.available_data,
        }

        for key, value in dict(**config).items():
            if value == "" or value is None:
                del config[key]

        config["release"] = config.pop("manager-release", None)
        return config

    def hash(self) -> int:
        """Calculate a hash of the current configuration."""
        json_str = json.dumps(self.config, sort_keys=True)
        hash = hashlib.sha256()
        hash.update(json_str.encode())
        return int(hash.hexdigest(), 16)

    def evaluate(self) -> Optional[str]:
        """Determine if manifest_config can be applied to manifests."""
        for prop in ["cloud-conf", "cluster-name"]:
            if not self.config.get(prop):
                return f"Provider manifests waiting for definition of {prop}"
        return None
