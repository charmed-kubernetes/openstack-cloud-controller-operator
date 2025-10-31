# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import random
import string

import pytest
import yaml
from lightkube import AsyncClient, KubeConfig
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Namespace

log = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def module_name(request):
    return request.module.__name__.replace("_", "-")


@pytest.fixture()
async def kubeconfig(ops_test):
    k_c_p = ops_test.model.applications["k8s"]
    (leader,) = [u for u in k_c_p.units if (await u.is_leader_from_status())]
    action = await leader.run_action("get-kubeconfig")
    action = await action.wait()
    success = (
        action.status == "completed"
        and action.results["return-code"] == 0
        and "kubeconfig" in action.results
    )

    if not success:
        logging.error(f"status: {action.status}")
        logging.error(f"results:\n{yaml.safe_dump(action.results, indent=2)}")
        pytest.fail("Failed to copy kubeconfig from k8s")

    kubeconfig_path = ops_test.tmp_path / "kubeconfig"
    with kubeconfig_path.open("w") as f:
        f.write(action.results["kubeconfig"])
    yield kubeconfig_path


@pytest.fixture()
async def kubernetes(kubeconfig, module_name):
    rand_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    namespace = f"{module_name}-{rand_str}"
    config = KubeConfig.from_file(kubeconfig)
    client = AsyncClient(
        config=config.get(context_name="k8s"),
        namespace=namespace,
        trust_env=False,
    )
    namespace_obj = Namespace(metadata=ObjectMeta(name=namespace))
    await client.create(namespace_obj)
    yield client
    await client.delete(Namespace, namespace)
