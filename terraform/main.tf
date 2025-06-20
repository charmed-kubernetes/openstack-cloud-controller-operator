# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "openstack_cloud_controller" {
  name  = var.app_name
  model = var.model

  charm {
    name     = "openstack-cloud-controller"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config      = var.config
}
