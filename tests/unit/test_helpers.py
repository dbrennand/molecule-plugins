"""Unit tests for small reusable helpers bundled with drivers."""

import copy
from types import SimpleNamespace

import pytest

from molecule_plugins.docker.playbooks.filter_plugins.get_docker_networks import (
    FilterModule,
    get_docker_networks,
)
from molecule_plugins.vagrant.modules.vagrant import VagrantClient, merge_dicts


def test_get_docker_networks_merges_labels_and_deduplicates_names():
    platforms = [
        {
            "docker_networks": [{"name": "shared", "labels": {"existing": "yes"}}],
            "networks": [{"name": "shared"}, {"name": "extra"}],
        },
    ]

    result = get_docker_networks(platforms, {"owner": "molecule"})

    assert result == [
        {
            "labels": {"existing": "yes", "owner": "molecule"},
            "name": "shared",
        },
        {"labels": {"owner": "molecule"}, "name": "extra"},
    ]


def test_get_docker_networks_accepts_empty_input():
    assert get_docker_networks([]) == []


def test_filter_module_registers_docker_network_filter():
    assert FilterModule().filters() == {
        "molecule_get_docker_networks": get_docker_networks,
    }


def test_merge_dicts_recurses_without_mutating_inputs():
    first = {"nested": {"left": 1}, "replace": [1], "unchanged": True}
    second = {"nested": {"right": 2}, "replace": [2]}
    original_first = copy.deepcopy(first)
    original_second = copy.deepcopy(second)

    result = merge_dicts(first, second)

    assert result == {
        "nested": {"left": 1, "right": 2},
        "replace": [2],
        "unchanged": True,
    }
    assert first == original_first
    assert second == original_second


def make_vagrant_client():
    """Create a Vagrant client without launching Vagrant."""

    def fail_json(*, msg):
        error = ValueError(msg)
        raise error

    client = object.__new__(VagrantClient)
    client._module = SimpleNamespace(  # noqa: SLF001
        fail_json=fail_json,
        params={"default_box": "debian/bookworm64", "provider_name": "virtualbox"},
        warn=lambda _message: None,
    )
    client.cachier = None
    client.provision = False
    return client


def test_vagrant_instance_config_uses_defaults_and_interface_options():
    client = make_vagrant_client()

    result = client._get_instance_vagrant_config_dict(  # noqa: SLF001
        {
            "interfaces": [
                {
                    "auto_config": True,
                    "network_name": "private_network",
                    "type": "dhcp",
                },
            ],
            "name": "node",
        },
    )

    assert result["box"] == "debian/bookworm64"
    assert result["cpus"] == 2
    assert result["hostname"] == "node"
    assert result["memory"] == 512
    assert result["provider"] == "virtualbox"
    assert result["networks"] == [
        {
            "name": "private_network",
            "options": {"auto_config": True, "type": "dhcp"},
        },
    ]


@pytest.mark.parametrize(
    "interface",
    [
        pytest.param({"type": "dhcp"}, id="missing-name"),
        pytest.param({"network_name": "invalid"}, id="invalid-name"),
    ],
)
def test_vagrant_instance_config_rejects_invalid_interfaces(interface):
    client = make_vagrant_client()

    with pytest.raises(ValueError, match="network_name"):
        client._get_instance_vagrant_config_dict(  # noqa: SLF001
            {"interfaces": [interface], "name": "node"},
        )


def test_vagrant_instance_config_requires_checksum_pair():
    client = make_vagrant_client()

    with pytest.raises(ValueError, match="must be used together"):
        client._get_instance_vagrant_config_dict(  # noqa: SLF001
            {"box_download_checksum": "abc123", "name": "node"},
        )
