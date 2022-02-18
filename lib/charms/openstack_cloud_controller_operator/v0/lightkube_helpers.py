# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helpers to make working with lightkube a little easier."""
import logging
from pathlib import Path

import yaml
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from lightkube.models.meta_v1 import ObjectMeta

# The unique Charmhub library identifier, never change it
LIBID = "4c2e312afbdf4b3f97bfab7667443ab7"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


log = logging.getLogger(__name__)


class LightKubeHelpers:
    """Helper for interacting with Kubernetes via lightkube."""

    def __init__(self, default_namespace):
        self.client = Client(namespace=default_namespace, field_manager="lightkube")

    def _fix_generic_list(self, manifest):
        # The kubectl CLI will automatically translate "kind: List" into a
        # concrete list type, but lightkube won't.
        # See the note at https://kubernetes.io/docs/reference/using-api/api-concepts/#collections
        resources = yaml.safe_load_all(manifest)
        for resource in resources:
            if resource["kind"] == "List":
                item_kind = resource["items"][0]["kind"]
                concrete_list = f"{item_kind}List"
                resource["kind"] = concrete_list
        return yaml.safe_dump_all(resources)

    def apply_manifest(self, manifest, namespace=None):
        """Apply all resources within a manifest.

        Arguments:
            manifest: Can be a Path or raw YAML text.
            namespace: Optional namespace to apply in.
        """
        if isinstance(manifest, Path):
            manifest = manifest.read_text()
        manifest = self._fix_generic_list(manifest)
        for obj in codecs.load_all_yaml(manifest):
            self.client.apply(obj, namespace=namespace)

    def delete_manifest(
        self, manifest, namespace=None, ignore_not_found=False, ignore_unauthorized=False
    ):
        """Delete all resources within a manifest.

        Arguments:
            manifest: Can be a Path or raw YAML text.
            namespace: Optional namespace to work in.
            ignore_not_found: If true, silently ignore missing resources.
            ignore_unauthorized: If true, silently ignore any Unauthorized errors.
        """
        if isinstance(manifest, Path):
            manifest = manifest.read_text()
        manifest = self._fix_generic_list(manifest)
        for obj in codecs.load_all_yaml(manifest):
            self.delete_object(
                type(obj),
                obj.metadata.name,
                namespace=namespace,
                ignore_not_found=ignore_not_found,
                ignore_unauthorized=ignore_unauthorized,
            )

    def apply_resource(self, resource_type, name, namespace=None, annotations=None, **kwargs):
        """Create or update a resource."""
        obj = resource_type(metadata=ObjectMeta(name=name, annotations=annotations), **kwargs)
        self.client.apply(obj, namespace=namespace)

    def delete_resource(
        self,
        resource_type,
        name,
        namespace=None,
        ignore_not_found=False,
        ignore_unauthorized=False,
    ):
        """Delete a resource."""
        try:
            self.client.delete(resource_type, name, namespace=namespace)
        except ApiError as err:
            log.exception("ApiError encountered while attempting to delete resource.")
            if err.status.message is not None:
                if "not found" in err.status.message and ignore_not_found:
                    log.error(f"Ignoring not found error:\n{err.status.message}")
                elif "(Unauthorized)" in err.status.message and ignore_unauthorized:
                    # Ignore error from https://bugs.launchpad.net/juju/+bug/1941655
                    log.error(f"Ignoring unauthorized error:\n{err.status.message}")
                else:
                    log.error(err.status.message)
                    raise
            else:
                raise
