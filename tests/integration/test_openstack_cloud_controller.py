# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import shlex
from pathlib import Path

import pytest
from lightkube.resources.core_v1 import Node

log = logging.getLogger(__name__)
CLOUD_CONF_OVERLAY = Path("tests/data/resources/empty.conf").resolve()


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test):
    charm = next(Path(".").glob("openstack-cloud-controller*.charm"), None)
    if not charm:
        log.info("Build Charm...")
        charm = await ops_test.build_charm(".")

    overlays = [Path("tests/data/charm.yaml")]
    config = {
        "charm": charm.resolve(),
        "resources": {"cloud-config-overlay": CLOUD_CONF_OVERLAY},
    }

    bundle, *overlays = await ops_test.async_render_bundles(*overlays, **config)

    log.info("Deploy Charm...")
    model = ops_test.model_full_name
    cmd = f"juju deploy -m {model} {bundle} --trust"
    rc, stdout, stderr = await ops_test.run(*shlex.split(cmd))
    assert rc == 0, f"Bundle deploy failed: {(stderr or stdout).strip()}"

    log.info(stdout)
    await ops_test.model.block_until(
        lambda: "openstack-cloud-controller" in ops_test.model.applications, timeout=60
    )

    await ops_test.model.wait_for_idle(wait_for_active=True, timeout=60 * 60)


async def test_provider_ids(kubernetes):
    async for node in kubernetes.list(Node):
        assert node.spec.providerID.startswith("openstack://")
