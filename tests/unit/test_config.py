# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the config module."""

import unittest.mock as mock

import pytest

from config import CharmConfig, merge_ini_configs


class TestMergeIniConfigs:
    """Tests for the merge_ini_configs function."""

    def test_merge_empty_base(self):
        """Test merging with empty base config."""
        base = ""
        override = "[LoadBalancer]\nsubnet-id = abc123\n"
        result = merge_ini_configs(base, override)
        assert "subnet-id = abc123" in result
        assert "[LoadBalancer]" in result

    def test_merge_empty_override(self):
        """Test merging with empty override config."""
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        override = ""
        result = merge_ini_configs(base, override)
        assert "auth-url = https://keystone.example.com" in result
        assert "[Global]" in result

    def test_merge_overlapping_sections(self):
        """Test that override values replace base values in same section."""
        base = "[LoadBalancer]\nsubnet-id = old-subnet\nlb-method = ROUND_ROBIN\n"
        override = "[LoadBalancer]\nsubnet-id = new-subnet\n"
        result = merge_ini_configs(base, override)
        assert "subnet-id = new-subnet" in result
        assert "lb-method = round_robin" in result.lower()
        assert "old-subnet" not in result

    def test_merge_new_section(self):
        """Test adding a new section from override."""
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        override = "[LoadBalancer]\nsubnet-id = abc123\n"
        result = merge_ini_configs(base, override)
        assert "[Global]" in result
        assert "[LoadBalancer]" in result
        assert "auth-url = https://keystone.example.com" in result
        assert "subnet-id = abc123" in result

    def test_merge_multiple_sections(self):
        """Test merging multiple sections from override."""
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        override = (
            "[LoadBalancer]\nsubnet-id = abc123\n"
            "[Networking]\ninternal-network-name = my-network\n"
        )
        result = merge_ini_configs(base, override)
        assert "[Global]" in result
        assert "[LoadBalancer]" in result
        assert "[Networking]" in result
        assert "internal-network-name = my-network" in result


class TestCharmConfig:
    """Tests for the CharmConfig class."""

    @pytest.fixture
    def mock_charm(self):
        """Create a mock charm object."""
        charm = mock.MagicMock()
        charm.config = {}
        return charm

    def test_init(self, mock_charm):
        """Test CharmConfig initialization."""
        config = CharmConfig(mock_charm)
        assert config.config == mock_charm.config
        assert config._secret_cloud_config is None

    def test_set_secret_cloud_config(self, mock_charm):
        """Test setting secret cloud config."""
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config("[LoadBalancer]\nsubnet-id = abc\n")
        assert config._secret_cloud_config == "[LoadBalancer]\nsubnet-id = abc\n"

    def test_available_data_filters_empty(self, mock_charm):
        """Test that available_data filters out empty and None values."""
        mock_charm.config = {
            "image-registry": "rocks.canonical.com",
            "empty-key": "",
            "none-key": None,
        }
        config = CharmConfig(mock_charm)
        assert "image-registry" in config.available_data
        assert "empty-key" not in config.available_data
        assert "none-key" not in config.available_data

    def test_get_layer3_ini_empty(self, mock_charm):
        """Test Layer 3 INI generation with no config set."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        result = config._get_charm_config_ini()
        assert result.strip() == ""

    def test_get_layer3_ini_with_values(self, mock_charm):
        """Test Layer 3 INI generation with charm config values."""
        mock_charm.config = {
            "load-balancer_member-subnet-id": "subnet-123",
        }
        config = CharmConfig(mock_charm)
        result = config._get_charm_config_ini()
        assert "[LoadBalancer]" in result
        assert "member-subnet-id = subnet-123" in result

    def test_merged_cloud_conf_layer1_only(self, mock_charm):
        """Test merged config with only Layer 1."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        result = config.merged_cloud_conf(base)
        assert "auth-url = https://keystone.example.com" in result

    def test_merged_cloud_conf_with_layer2(self, mock_charm):
        """Test merged config with Layer 1 and Layer 2."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config("[LoadBalancer]\nsubnet-id = secret-subnet\n")
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        result = config.merged_cloud_conf(base)
        assert "auth-url = https://keystone.example.com" in result
        assert "subnet-id = secret-subnet" in result

    def test_merged_cloud_conf_with_layer3(self, mock_charm):
        """Test merged config with all three layers."""
        mock_charm.config = {
            "load-balancer_member-subnet-id": "charm-member-subnet",
        }
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config("[LoadBalancer]\nmember-subnet-id = secret-member-subnet\n")
        base = "[Global]\nauth-url = https://keystone.example.com\n"
        result = config.merged_cloud_conf(base)
        assert "auth-url = https://keystone.example.com" in result
        assert "member-subnet-id = charm-member-subnet" in result
        assert "secret-member-subnet" not in result

    def test_merged_cloud_conf_layer2_overrides_layer1(self, mock_charm):
        """Test that Layer 2 overrides Layer 1."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config(
            "[LoadBalancer]\nsubnet-id = secret-subnet\nlb-method = LEAST_CONNECTIONS\n"
        )
        base = "[LoadBalancer]\nsubnet-id = integrator-subnet\nlb-method = ROUND_ROBIN\n"
        result = config.merged_cloud_conf(base)
        assert "subnet-id = secret-subnet" in result
        assert "lb-method = least_connections" in result.lower()
        assert "integrator-subnet" not in result

    def test_evaluate_valid_config(self, mock_charm):
        """Test evaluate returns None for valid config."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        assert config.evaluate() is None

    def test_evaluate_valid_secret(self, mock_charm):
        """Test evaluate returns None for valid secret INI."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config("[LoadBalancer]\nsubnet-id = abc\n")
        assert config.evaluate() is None

    def test_evaluate_invalid_secret_ini(self, mock_charm):
        """Test evaluate returns error for invalid INI in secret."""
        mock_charm.config = {}
        config = CharmConfig(mock_charm)
        config.set_secret_cloud_config("subnet-id = abc\n")
        result = config.evaluate()
        assert result is not None
        assert "Invalid cloud-config secret" in result
