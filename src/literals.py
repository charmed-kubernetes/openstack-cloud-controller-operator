# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Literal constants for the cloud-controller-manager charm."""

# INI Section Names
LOADBALANCER_SECTION = "LoadBalancer"

# LoadBalancer INI Keys
LB_MEMBER_SUBNET_ID = "member-subnet-id"

# Charm Config Option Names
CHARM_LB_MEMBER_SUBNET_ID = "load-balancer_member-subnet-id"

# Mapping of charm config options to INI (section, key) tuples
CHARM_TO_INI_MAP = {
    CHARM_LB_MEMBER_SUBNET_ID: (LOADBALANCER_SECTION, LB_MEMBER_SUBNET_ID),
}
