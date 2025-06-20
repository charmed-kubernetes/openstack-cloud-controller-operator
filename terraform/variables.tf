# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Name of the application in the Juju model."
  type        = string
  default     = "openstack-cloud-controller"
}

variable "base" {
  description = "Ubuntu bases to deploy the charm onto"
  type        = string
  default     = "ubuntu@22.04"

  validation {
    condition     = contains(["ubuntu@22.04", "ubuntu@24.04"], var.base)
    error_message = "Base must be one of ubuntu@22.04, ubuntu@24.04"
  }
}

variable "channel" {
  description = "The channel to use when deploying a charm."
  type        = string
  default     = "1.33/stable"
}

variable "config" {
  description = "Application config. Details about available options can be found at https://charmhub.io/openstack-cloud-controller/configurations."
  type        = map(string)
  default     = {}
}

variable "model" {
  description = "Reference to a `juju_model`."
  type        = string
}

variable "revision" {
  description = "Revision number of the charm"
  type        = number
  default     = null
}
