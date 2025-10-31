# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config Management for the cloud-controller-manager charm."""

import configparser
import io
import logging
from functools import lru_cache as cached
from typing import Mapping, Optional, Union

import ops

log = logging.getLogger(__name__)
CLOUD_CONF_OVERLAY = "cloud-config-overlay"


class CharmConfig:
    """Representation of the charm configuration."""

    def __init__(self, charm: ops.CharmBase):
        """Creates a CharmConfig object from the configuration data."""
        self.charm = charm

    @property
    def available_data(self):
        """Parse valid charm config into a dict, drop keys if unset."""
        data: Mapping[str, Union[bool, int, float, str]] = {}
        for key, value in dict(**self.charm.config).items():
            if value == "" or value is None:
                del data[key]
        return data

    @cached
    def _load_cloud_config(self) -> Optional[str]:
        """Load the cloud config from the charm resource."""
        try:
            meta = self.charm.meta.resources[CLOUD_CONF_OVERLAY]
            path = self.charm.model.resources.fetch(meta.resource_name)
            log.info("Loaded cloud config overlay from resource (size: %d)", path.stat().st_size)
            return path.read_text()
        except (NameError, ops.ModelError) as e:
            log.warning("Failed to read cloud config from resource. %s", e)
            return None

    def _validate_cloud_config(self) -> Optional[str]:
        """Validate the provided cloud config string."""
        if not (overlay := self._load_cloud_config()):
            return None

        parser = configparser.ConfigParser()
        try:
            parser.read_string(overlay)
        except configparser.Error as e:
            log.error("Invalid cloud-config-overlay provided. %s", e)
            return "Invalid cloud-config-overlay"
        return None

    def merge_cloud_config(self, merge_from: Optional[str]) -> str:
        """Merge charm config with provided cloud config dict."""
        self.charm

        overlay = self._load_cloud_config() or ""
        base = merge_from or ""
        if base and overlay:
            log.info("Applying cloud-config-overlay from charm resource.")
            charm = configparser.ConfigParser()
            charm.read_string(str(overlay))

            source = configparser.ConfigParser()
            source.read_string(base)

            output = configparser.ConfigParser()
            final = {}
            for section in set(source.sections()).union(set(charm.sections())):
                left = source[section] if source.has_section(section) else {}
                right = charm[section] if charm.has_section(section) else {}
                final[section] = {**left, **right}
            output.read_dict(final)

            with io.StringIO() as str_io:
                output.write(str_io)
                base = str_io.getvalue()

        return base

    def evaluate(self) -> Optional[str]:
        """Determine if configuration is valid."""
        return self._validate_cloud_config()
