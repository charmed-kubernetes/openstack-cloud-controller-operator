# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Library for cloud_config interface."""

from serialized_data_interface.relation import EndpointWrapper
from serialized_data_interface.testing import MockRemoteRelationMixin

# The unique Charmhub library identifier, never change it
LIBID = "fcd5966366594e858e8d15f711494dd0"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


_SCHEMA = {
    "v1": {
        "flat": True,
        "provides": {
            "app": {
                "type": "object",
                "required": ["config_hash"],
                "properties": {
                    "config_hash": {"type": "string"},
                },
            },
        },
    },
}


class CloudConfigRequires(EndpointWrapper):
    """Requires side of openstack-integration relation."""

    INTERFACE = "cloud_config"
    ROLE = "requires"
    LIMIT = 1
    SCHEMA = _SCHEMA

    @property
    def relation(self):
        """The remote relation, or None."""
        if not self.relations:
            return None
        return self.relations[0]

    @property
    def config_hash(self):
        """The MD5 hash of the OpenStack cloud-config, used to detect changes."""
        if not self.is_ready(self.relation):
            return None
        data = self.unwrap(self.relation)
        return data[self.relation.app]["config_hash"]


class CloudConfigProvides(EndpointWrapper):
    """Provides side of openstack-integration relation."""

    INTERFACE = "cloud_config"
    ROLE = "provides"
    SCHEMA = _SCHEMA

    def send_hash(self, hash):
        """Send the hash of the config data to the listeners to notify them of changes."""
        for relation in self.relations:
            if not self.is_available(relation):
                continue
            self.wrap(relation, {self.app: {"config_hash": hash}})


class MockCloudConfigRequires(MockRemoteRelationMixin, CloudConfigRequires):
    """Testing wrapper for CloudConfigRequires."""

    @property
    def config_hash(self):
        """The MD5 hash of the OpenStack cloud-config, used to detect changes."""
        with self.remote_context(self.relation):
            return super().config_hash


class MockCloudConfigProvides(MockRemoteRelationMixin, CloudConfigProvides):
    """Testing wrapper for CloudConfigProvides."""

    pass
