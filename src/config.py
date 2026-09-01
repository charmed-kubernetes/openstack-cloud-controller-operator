# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config Management for the cloud-controller-manager charm."""

import configparser
import io
import logging
from typing import Optional

from literals import CHARM_TO_INI_MAP

log = logging.getLogger(__name__)


def merge_ini_configs(base_ini: str, override_ini: str) -> str:
    """Merge two INI config strings, with override taking precedence.

    Args:
        base_ini: The base INI configuration string.
        override_ini: The override INI configuration string.

    Returns:
        Merged INI configuration as a string.
    """
    base = configparser.ConfigParser()
    base.read_string(base_ini)

    override = configparser.ConfigParser()
    override.read_string(override_ini)

    for section in override.sections():
        if not base.has_section(section):
            base.add_section(section)
        for key, value in override.items(section):
            base.set(section, key, value)

    output = io.StringIO()
    base.write(output)
    return output.getvalue()


class CharmConfig:
    """Representation of the charm configuration."""

    def __init__(self, charm):
        """Creates a CharmConfig object from the configuration data."""
        self.config = charm.config
        self._charm = charm
        self._secret_cloud_config: Optional[str] = None

    def set_secret_cloud_config(self, content: Optional[str]) -> None:
        """Set the cloud-config content from the Juju secret.

        Args:
            content: INI-formatted cloud-config string from the secret.
        """
        self._secret_cloud_config = content

    @property
    def available_data(self):
        """Parse valid charm config into a dict, drop keys if unset."""
        data = {**self.config}
        for key, value in {**self.config}.items():
            if value == "" or value is None:
                del data[key]

        return data

    def _get_charm_config_ini(self) -> str:
        """Build INI string from charm config options.

        Returns:
            INI-formatted string with charm config overrides.
        """
        parser = configparser.ConfigParser()

        for charm_key, (section, ini_key) in CHARM_TO_INI_MAP.items():
            value = self.config.get(charm_key)
            if value is not None and value != "":
                if not parser.has_section(section):
                    parser.add_section(section)
                if isinstance(value, bool):
                    value = str(value).lower()
                else:
                    value = str(value)
                parser.set(section, ini_key, value)

        output = io.StringIO()
        parser.write(output)
        return output.getvalue()

    def merged_cloud_conf(self, base_cloud_conf: str) -> str:
        """Merge cloud-config from all three layers.

        Layer 1: Base config from OpenStack Integrator (lowest priority)
        Layer 2: User provided Juju secret config
        Layer 3: Charm configuration options (highest priority)

        Args:
            base_cloud_conf: The base cloud-config INI string from the integrator.

        Returns:
            Merged cloud-config as an INI-formatted string.
        """
        result = base_cloud_conf

        if self._secret_cloud_config:
            result = merge_ini_configs(result, self._secret_cloud_config)

        charm_config_ini = self._get_charm_config_ini()
        if charm_config_ini.strip():
            result = merge_ini_configs(result, charm_config_ini)

        return result

    def evaluate(self) -> Optional[str]:
        """Determine if configuration is valid.

        Returns:
            Error message if configuration is invalid, None otherwise.
        """
        if self._secret_cloud_config:
            try:
                parser = configparser.ConfigParser()
                parser.read_string(self._secret_cloud_config)
            except configparser.Error as e:
                # Log only the exception type, not the full traceback or message,
                # as it may contain sensitive credentials from the cloud-config.
                log.error(
                    "Invalid INI format in cloud-config secret: %s",
                    type(e).__name__,
                )
                return "Invalid cloud-config secret format."

        return None
