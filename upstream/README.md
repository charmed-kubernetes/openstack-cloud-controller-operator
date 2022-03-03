# Upstream Manifests

This directory contains local copies of the upstream manifests from the release
commit supported by this charm to be used by the charm for deployment. These
files should not be modified locally.

## Updating

To update these, simply run the update script, passing in the release branch,
tag, or commit to update to:

```bash
./upstream/update.sh release-1.23
```

This will overwrite the existing manifests for the supported components, update
the list of image resources in `metadata.yaml`, and, finally, update the
`ref.sha` file with the resolved ref information for the new version.
