# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Implementation of openstack-integration interface.

This only implements the requires side, currently, since the integrator
is still using the Reactive Charm frameworkself.
"""
import json
import logging
from functools import cached_property

from ops.framework import Object

# The unique Charmhub library identifier, never change it
LIBID = "b9ffb8ffd72c427eab998c2ea335141a"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


log = logging.getLogger(__name__)


# Can't use EndpointWrapper from SDI because the integrator can't do
# the version negotiation. :(
class OpenStackIntegrationRequires(Object):
    """Requires side of openstack-integration relation."""

    LIMIT = 1
    SCHEMA = {
        "type": "object",
        "properties": {
            "auth_url": {"type": "string"},
            "region": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "user_domain_name": {"type": "string"},
            "project_domain_name": {"type": "string"},
            "project_name": {"type": "string"},
            "endpoint_tls_ca": {"type": "string"},
            "version": {"type": "string"},
            "subnet_id": {"type": "string"},
            "floating_network_id": {"type": "string"},
            "lb_method": {"type": "string"},
            "manage_security_groups": {"type": "boolean"},
            "bs_version": {"type": "string"},
            "trust_device_path": {"type": "string"},
            "ignore_volume_az": {"type": "boolean"},
            "has_octavia": {"type": "boolean"},
        },
    }
    IGNORE_FIELDS = {
        "egress-subnets",
        "ingress-address",
        "private-address",
    }

    def __init__(self, charm, endpoint="openstack-integration"):
        super().__init__(charm, f"relation-{endpoint}")
        self.charm = charm
        self.endpoint = endpoint

    @cached_property
    def relation(self):
        """The relation to the integrator, or None."""
        return self.model.get_relation(self.endpoint)

    @cached_property
    def _data(self):
        if not (self.relation and self.relation.units):
            return {}
        raw_data = self.relation.data[list(self.relation.units)[0]]
        data = {}
        for field, raw_value in raw_data.items():
            if field in self.IGNORE_FIELDS or not raw_value:
                continue
            try:
                data[field] = json.loads(raw_value)
            except json.JSONDecodeError as e:
                log.error(f"Failed to decode relation data in {field}: {e}")
        return data

    def _value(self, key):
        if not self._data:
            return None
        return self._data.get(key)

    @property
    def auth_url(self):
        """The auth_url value."""
        return self._value("auth_url")

    @property
    def region(self):
        """The region value."""
        return self._value("region")

    @property
    def username(self):
        """The username value."""
        return self._value("username")

    @property
    def password(self):
        """The password value."""
        return self._value("password")

    @property
    def user_domain_name(self):
        """The user_domain_name value."""
        return self._value("user_domain_name")

    @property
    def project_domain_name(self):
        """The project_domain_name value."""
        return self._value("project_domain_name")

    @property
    def project_name(self):
        """The project_name value."""
        return self._value("project_name")

    @property
    def endpoint_tls_ca(self):
        """The endpoint_tls_ca value."""
        return self._value("endpoint_tls_ca")

    @property
    def version(self):
        """The version value."""
        return self._value("version")

    @property
    def subnet_id(self):
        """The subnet_id value."""
        return self._value("subnet_id")

    @property
    def floating_network_id(self):
        """The floating_network_id value."""
        return self._value("floating_network_id")

    @property
    def lb_method(self):
        """The lb_method value."""
        return self._value("lb_method")

    @property
    def manage_security_groups(self):
        """The manage_security_groups value."""
        return self._value("manage_security_groups")

    @property
    def bs_version(self):
        """The bs_version value."""
        return self._value("bs_version")

    @property
    def trust_device_path(self):
        """The trust_device_path value."""
        return self._value("trust_device_path")

    @property
    def ignore_volume_az(self):
        """The ignore_volume_az value."""
        return self._value("ignore_volume_az")

    @property
    def has_octavia(self):
        """The has_octavia value."""
        return self._value("has_octavia")
