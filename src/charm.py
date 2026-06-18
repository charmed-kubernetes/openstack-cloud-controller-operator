#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Deploy and manage the Controller-Manager for K8s on OpenStack."""

import base64
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import ops
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.resources.core_v1 import Node
from openstack import connection as openstack_connection
from ops.interface_kube_control import KubeControlRequirer
from ops.interface_openstack_integration import OpenstackIntegrationRequirer
from ops.interface_tls_certificates import CertificatesRequires
from ops.manifests import Collector, ManifestClientError

from config import CharmConfig
from provider_manifests import ProviderManifests

log = logging.getLogger(__name__)

# Maximum number of node names to display in status messages
MAX_NODES_IN_STATUS = 3


class ProviderCharm(ops.CharmBase):
    """Deploy and manage the Cloud Controller Manager for K8s on OpenStack."""

    stored = ops.StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        # Ensure kubeconfig environment
        self._kubeconfig_path.parent.mkdir(parents=True, exist_ok=True)

        # Relation Validator and datastore
        self.kube_control = KubeControlRequirer(self, schemas="0,1")
        self.certificates = CertificatesRequires(self)
        self.integrator = OpenstackIntegrationRequirer(self)
        # Config Validator and datastore
        self.charm_config = CharmConfig(self)

        self.stored.set_default(
            config_hash=None,  # hashed value of the config once valid
            deployed=False,  # True if the config has been applied after new hash
        )
        self.collector = Collector(
            ProviderManifests(self, self.charm_config, self.kube_control, self.integrator),
        )

        self.framework.observe(self.on.kube_control_relation_created, self._kube_control)
        self.framework.observe(self.on.kube_control_relation_joined, self._kube_control)
        self.framework.observe(self.on.kube_control_relation_changed, self._merge_config)
        self.framework.observe(self.on.kube_control_relation_departed, self._pre_teardown)
        self.framework.observe(self.on.kube_control_relation_broken, self._merge_config)

        self.framework.observe(self.on.certificates_relation_created, self._merge_config)
        self.framework.observe(self.on.certificates_relation_changed, self._merge_config)
        self.framework.observe(self.on.certificates_relation_broken, self._merge_config)

        self.framework.observe(self.on.external_cloud_provider_relation_joined, self._merge_config)
        self.framework.observe(self.on.external_cloud_provider_relation_broken, self._merge_config)

        self.framework.observe(self.on.openstack_relation_created, self._merge_config)
        self.framework.observe(self.on.openstack_relation_joined, self._merge_config)
        self.framework.observe(self.on.openstack_relation_changed, self._merge_config)
        self.framework.observe(self.on.openstack_relation_departed, self._pre_teardown)
        self.framework.observe(self.on.openstack_relation_broken, self._merge_config)

        self.framework.observe(self.on.list_versions_action, self._list_versions)
        self.framework.observe(self.on.list_resources_action, self._list_resources)
        self.framework.observe(self.on.scrub_resources_action, self._scrub_resources)
        self.framework.observe(self.on.sync_resources_action, self._sync_resources)
        self.framework.observe(self.on.update_status, self._update_status)

        self.framework.observe(self.on.install, self._install_or_upgrade)
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.on.config_changed, self._merge_config)
        self.framework.observe(self.on.stop, self._cleanup)

    @property
    def _ca_cert_path(self) -> Path:
        return Path(f"/srv/{self.unit.name}/ca.crt")

    @property
    def _kubeconfig_path(self) -> Path:
        path = f"/srv/{self.unit.name}/kubeconfig"
        os.environ["KUBECONFIG"] = path
        return Path(path)

    @property
    def _openstack_ca_cert_path(self) -> Path:
        return Path(f"/srv/{self.unit.name}/openstack-endpoint-ca.crt")

    def _list_versions(self, event):
        self.collector.list_versions(event)

    def _list_resources(self, event):
        manifests = event.params.get("controller", "")
        resources = event.params.get("resources", "")
        return self.collector.list_resources(event, manifests, resources)

    def _scrub_resources(self, event):
        manifests = event.params.get("controller", "")
        resources = event.params.get("resources", "")
        return self.collector.scrub_resources(event, manifests, resources)

    def _sync_resources(self, event):
        manifests = event.params.get("controller", "")
        resources = event.params.get("resources", "")
        try:
            self.collector.apply_missing_resources(event, manifests, resources)
        except ManifestClientError:
            msg = "Failed to apply missing resources. API Server unavailable."
            event.set_results({"result": msg})

    @staticmethod
    def _decode_relation_value(value):
        """Decode quoted JSON-style relation values into native Python values."""
        if not isinstance(value, str):
            return value
        value = value.strip()
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _openstack_relation_data(self) -> Dict[str, str]:
        """Return the remote relation data for the openstack relation."""
        relation = getattr(self.integrator, "relation", None)
        if not relation or not relation.units:
            return {}
        try:
            unit = next(iter(relation.units))
        except StopIteration:
            return {}
        return dict(relation.data[unit])

    def _openstack_connection(self) -> Optional[openstack_connection.Connection]:
        """Build an OpenStack SDK connection from relation data."""
        relation_data = self._openstack_relation_data()
        if not relation_data:
            log.info("OpenStack relation data is not yet available for providerID lookup.")
            return None

        decoded = {key: self._decode_relation_value(value) for key, value in relation_data.items()}
        auth_url = decoded.get("auth_url")
        if not auth_url:
            log.warning("OpenStack relation data is missing auth_url; cannot resolve providerIDs.")
            return None

        conn_args = {
            "auth_url": auth_url,
            "region_name": decoded.get("region") or None,
            "identity_api_version": str(decoded.get("version") or "3"),
        }

        endpoint_tls_ca = decoded.get("endpoint_tls_ca")
        if endpoint_tls_ca:
            self._openstack_ca_cert_path.write_bytes(base64.b64decode(endpoint_tls_ca))
            conn_args["verify"] = str(self._openstack_ca_cert_path)

        if decoded.get("application_credential_id") and decoded.get(
            "application_credential_secret"
        ):
            conn_args.update(
                {
                    "auth_type": "v3applicationcredential",
                    "application_credential_id": decoded["application_credential_id"],
                    "application_credential_secret": decoded["application_credential_secret"],
                }
            )
            log.info("Using OpenStack application credentials for providerID lookup.")
        else:
            required = {
                "username": decoded.get("username"),
                "password": decoded.get("password"),
                "project_name": decoded.get("project_name"),
                "user_domain_name": decoded.get("user_domain_name"),
                "project_domain_name": decoded.get("project_domain_name"),
            }
            missing = [key for key, value in required.items() if not value]
            if missing:
                log.warning(
                    "OpenStack relation data is missing %s; cannot resolve providerIDs.",
                    ", ".join(sorted(missing)),
                )
                return None
            conn_args.update(required)
            log.info("Using OpenStack username/password credentials for providerID lookup.")

        return openstack_connection.Connection(**conn_args)

    @staticmethod
    def _node_internal_ip(node: Node) -> Optional[str]:
        """Extract the first InternalIP from a Kubernetes node."""
        for address in getattr(node.status, "addresses", []) or []:
            if address.type == "InternalIP" and address.address:
                return address.address
        return None

    @staticmethod
    def _server_ips(server) -> List[str]:
        """Extract all IP addresses from an OpenStack server object."""
        ips = []
        for network in (getattr(server, "addresses", {}) or {}).values():
            if not isinstance(network, list):
                continue
            for address in network:
                if isinstance(address, dict) and address.get("addr"):
                    ips.append(address["addr"])
        return ips

    def _servers_by_internal_ip(self) -> Dict[str, List[str]]:
        """Map OpenStack server IPs to providerID values."""
        conn = self._openstack_connection()
        if not conn:
            return {}

        servers_by_ip: Dict[str, List[str]] = {}
        for server in conn.compute.servers(details=True):
            provider_id = f"openstack:///{server.id}"
            for ip in self._server_ips(server):
                servers_by_ip.setdefault(ip, []).append(provider_id)
        log.info(
            "Loaded %d OpenStack server IP mappings for providerID lookup.", len(servers_by_ip)
        )
        return servers_by_ip

    def _check_node_provider_ids(self) -> List[str]:
        """Check nodes for missing or invalid providerIDs.

        Returns:
            List of node names that are missing or have invalid providerIDs.
        """
        try:
            client = Client()
            nodes_without_provider_id = []
            servers_by_ip = self._servers_by_internal_ip()

            for node in client.list(Node):
                provider_id = node.spec.providerID if node.spec.providerID else ""
                # Expected format: "openstack://region/InstanceID" or "openstack:///InstanceID"
                if not provider_id.startswith("openstack://"):
                    internal_ip = self._node_internal_ip(node)
                    if not internal_ip:
                        log.info(
                            "Node %s has no InternalIP; cannot resolve providerID.",
                            node.metadata.name,
                        )
                        nodes_without_provider_id.append(node.metadata.name)
                        continue

                    matches = servers_by_ip.get(internal_ip, [])
                    if len(matches) > 1:
                        log.warning(
                            "Found multiple OpenStack matches for node %s InternalIP %s; skipping providerID patch.",
                            node.metadata.name,
                            internal_ip,
                        )
                        nodes_without_provider_id.append(node.metadata.name)
                        continue
                    if not matches:
                        log.info(
                            "No OpenStack server match found for node %s InternalIP %s.",
                            node.metadata.name,
                            internal_ip,
                        )
                        nodes_without_provider_id.append(node.metadata.name)
                        continue

                    patched_provider_id = matches[0]
                    log.info(
                        "Patching providerID for node %s using InternalIP %s -> %s.",
                        node.metadata.name,
                        internal_ip,
                        patched_provider_id,
                    )
                    client.patch(
                        Node, node.metadata.name, {"spec": {"providerID": patched_provider_id}}
                    )

            return nodes_without_provider_id
        except ApiError as e:
            log.warning("Failed to query nodes for providerIDs: %s", e)
            return []

    def _update_status(self, _):
        if not self.stored.deployed:
            return

        unready = self.collector.unready
        if unready:
            self.unit.status = ops.WaitingStatus(", ".join(unready))
            return

        # Check if nodes have providerIDs set (bug #2100952)
        nodes_without_provider_id = self._check_node_provider_ids()
        if nodes_without_provider_id:
            node_list = ", ".join(nodes_without_provider_id[:MAX_NODES_IN_STATUS])
            suffix = (
                f" (+{len(nodes_without_provider_id) - MAX_NODES_IN_STATUS} more)"
                if len(nodes_without_provider_id) > MAX_NODES_IN_STATUS
                else ""
            )
            self.unit.status = ops.WaitingStatus(
                f"Cloud provider not initialized on nodes: {node_list}{suffix}"
            )
            return

        self.unit.status = ops.ActiveStatus("Ready")
        self.unit.set_workload_version(self.collector.short_version)
        if self.unit.is_leader():
            self.app.status = ops.ActiveStatus(self.collector.long_version)

    def _kube_control(self, event):
        self.kube_control.set_auth_request(self.unit.name, "system:masters")
        return self._merge_config(event)

    def _check_integrator(self, event):
        self.unit.status = ops.MaintenanceStatus("Evaluating Openstack relation.")
        evaluation = self.integrator.evaluate_relation(event)
        if evaluation:
            if "Waiting" in evaluation:
                self.unit.status = ops.WaitingStatus(evaluation)
            else:
                self.unit.status = ops.BlockedStatus(evaluation)
            return False
        return True

    def _check_kube_control(self, event):
        self.unit.status = ops.MaintenanceStatus("Evaluating kubernetes authentication.")
        evaluation = self.kube_control.evaluate_relation(event)
        if evaluation:
            if "Waiting" in evaluation:
                self.unit.status = ops.WaitingStatus(evaluation)
            else:
                self.unit.status = ops.BlockedStatus(evaluation)
            return False
        if not self.kube_control.get_auth_credentials(self.unit.name):
            self.unit.status = ops.WaitingStatus("Waiting for kube-control: unit credentials")
            return False
        self.kube_control.create_kubeconfig(
            self._ca_cert_path, self._kubeconfig_path, "root", self.unit.name
        )
        return True

    def _check_certificates(self, event):
        if self.kube_control.get_ca_certificate():
            log.info("CA Certificate is available from kube-control.")
            return True

        self.unit.status = ops.MaintenanceStatus("Evaluating certificates.")
        evaluation = self.certificates.evaluate_relation(event)
        if evaluation:
            if "Waiting" in evaluation:
                self.unit.status = ops.WaitingStatus(evaluation)
            else:
                self.unit.status = ops.BlockedStatus(evaluation)
            return False
        self._ca_cert_path.write_text(self.certificates.ca)
        return True

    def _check_config(self):
        self.unit.status = ops.MaintenanceStatus("Evaluating charm config.")
        evaluation = self.charm_config.evaluate()
        if evaluation:
            self.unit.status = ops.BlockedStatus(evaluation)
            return False
        return True

    def _merge_config(self, event):
        if not self._check_integrator(event):
            return

        if not self._check_certificates(event):
            return

        if not self._check_kube_control(event):
            return

        if not self._check_config():
            return

        self.unit.status = ops.MaintenanceStatus("Evaluating Manifests")
        new_hash = 0
        for controller in self.collector.manifests.values():
            evaluation = controller.evaluate()
            if evaluation:
                self.unit.status = ops.BlockedStatus(evaluation)
                return
            new_hash += controller.hash()

        self.stored.deployed = False
        if self._install_or_upgrade(event, config_hash=new_hash):
            self.stored.config_hash = new_hash
            self.stored.deployed = True

    def _install_or_upgrade(self, event, config_hash=None):
        if self.stored.config_hash == config_hash:
            log.info("Skipping until the config is evaluated.")
            return True

        if not self.unit.is_leader():
            self.unit.status = ops.ActiveStatus("Ready (standby)")
            log.info("Skipping manifest apply on non-leader unit")
            return True

        self.unit.status = ops.MaintenanceStatus("Deploying Cloud Controller Manager")
        self.unit.set_workload_version("")
        for controller in self.collector.manifests.values():
            try:
                controller.apply_manifests()
            except ManifestClientError as e:
                self.unit.status = ops.WaitingStatus("Waiting for kube-apiserver")
                log.warning(f"Encountered installation error: {e}")
                event.defer()
                return False
        return True

    def _pre_teardown(self, event):
        """Delete manifests before a relation is removed, while credentials are still valid."""
        if not self.unit.is_leader() or not self.stored.config_hash:
            return
        if self.app.planned_units() != 0:
            return
        self.unit.status = ops.MaintenanceStatus("Cleaning up Cloud Controller Manager")
        for controller in self.collector.manifests.values():
            try:
                controller.delete_manifests(ignore_unauthorized=True)
            except ManifestClientError:
                log.warning("Failed to delete manifests during relation teardown")
        self.stored.config_hash = None

    def _cleanup(self, event):
        self.unit.status = ops.MaintenanceStatus("Shutting down")
        if self._kubeconfig_path.parent.is_dir() and self._kubeconfig_path.parent.exists():
            shutil.rmtree(self._kubeconfig_path.parent)
        elif self._kubeconfig_path.parent.exists():
            # Note(Hue): This should never happen but whatever I guess...
            self._kubeconfig_path.parent.unlink(missing_ok=True)


if __name__ == "__main__":
    ops.main(ProviderCharm)
