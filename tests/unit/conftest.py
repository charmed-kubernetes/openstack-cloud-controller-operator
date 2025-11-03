# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest.mock as mock

import pytest


@pytest.fixture(autouse=True)
def lk_client():
    with mock.patch("ops.manifests.manifest.Client", autospec=True) as mock_lightkube:
        yield mock_lightkube.return_value


@pytest.fixture(autouse=True)
def lk_client_charm():
    with mock.patch("charm.Client", autospec=True) as mock_client:
        # Mock the client.list() to return empty list by default (no nodes)
        mock_client.return_value.list.return_value = []
        yield mock_client.return_value
