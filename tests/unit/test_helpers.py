"""Unit tests for small reusable helpers bundled with drivers."""

import copy
import subprocess
from types import SimpleNamespace

import pytest

from molecule_plugins.docker.playbooks.filter_plugins.get_docker_networks import (
    FilterModule,
    get_docker_networks,
)
from molecule_plugins.vagrant.modules.vagrant import VagrantClient, merge_dicts


def test_get_docker_networks_merges_labels_and_deduplicates_names():
    """Verify Docker networks merge labels and deduplicate names."""
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
    """Verify no networks are returned for empty platform input."""
    assert get_docker_networks([]) == []


def test_filter_module_registers_docker_network_filter():
    """Verify the Ansible filter module registers the Docker network filter."""
    assert FilterModule().filters() == {
        "molecule_get_docker_networks": get_docker_networks,
    }


def test_merge_dicts_recurses_without_mutating_inputs():
    """Verify dictionary merging recurses without mutating either input."""
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
        """Raise the simulated Ansible module failure."""
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
    """Verify Vagrant configuration applies defaults and interface options."""
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
    """Verify invalid Vagrant interfaces raise a descriptive error."""
    client = make_vagrant_client()

    with pytest.raises(ValueError, match="network_name"):
        client._get_instance_vagrant_config_dict(  # noqa: SLF001
            {"interfaces": [interface], "name": "node"},
        )


def test_vagrant_instance_config_requires_checksum_pair():
    """Verify checksum metadata must be supplied as a complete pair."""
    client = make_vagrant_client()

    with pytest.raises(ValueError, match="must be used together"):
        client._get_instance_vagrant_config_dict(  # noqa: SLF001
            {"box_download_checksum": "abc123", "name": "node"},
        )


def test_vagrant_instance_config_translates_rich_platform_data():
    """Verify a rich platform maps to the normalized Vagrant configuration."""
    client = make_vagrant_client()

    result = client._get_instance_vagrant_config_dict(  # noqa: SLF001
        {
            "name": "web",
            "hostname": "web.example.test",
            "cpus": 4,
            "memory": 2048,
            "box": "debian/bookworm64",
            "box_url": "https://example.test/bookworm.box",
            "box_version": "1.2.3",
            "box_architecture": "amd64",
            "box_download_checksum": "abc123",
            "box_download_checksum_type": "sha256",
            "config_options": {
                "synced_folder": False,
                "ssh.insert_key": False,
                "vm.network": {"type": "private_network"},
            },
            "provider_options": {"gui": True, "memory": 4096},
            "provider_raw_config_args": ["custom = true"],
            "provider_override_args": ["memory = 8192"],
            "instance_raw_config_args": ["vm.box_check_update = false"],
            "interfaces": [
                {"network_name": "forwarded_port", "guest": 8080, "host": 18080},
            ],
        },
    )

    assert result == {
        "name": "web",
        "hostname": "web.example.test",
        "memory": 2048,
        "cpus": 4,
        "networks": [
            {
                "name": "forwarded_port",
                "options": {"guest": 8080, "host": 18080},
            },
        ],
        "instance_raw_config_args": ["vm.box_check_update = false"],
        "config_options": {
            "synced_folder": False,
            "ssh.insert_key": False,
            "vm.network": {"type": "private_network"},
        },
        "box": "debian/bookworm64",
        "box_version": "1.2.3",
        "box_url": "https://example.test/bookworm.box",
        "box_architecture": "amd64",
        "box_download_checksum": "abc123",
        "box_download_checksum_type": "sha256",
        "provider": "virtualbox",
        "provider_options": {"gui": True, "memory": 4096},
        "provider_raw_config_args": ["custom = true"],
        "provider_override_args": ["memory = 8192"],
    }


def test_write_vagrantfile_renders_two_nodes_and_selected_options(tmp_path):
    """Verify rendering includes both nodes and representative Vagrant options."""
    client = make_vagrant_client()
    client._vagrantfile = str(tmp_path / "Vagrantfile")  # noqa: SLF001
    client._get_vagrant_config_dict = lambda: [  # noqa: SLF001
        {
            "name": "web",
            "hostname": "web",
            "box": "debian/bookworm64",
            "box_version": None,
            "box_url": None,
            "box_architecture": None,
            "box_download_checksum": None,
            "box_download_checksum_type": None,
            "config_options": {"synced_folder": False, "ssh.insert_key": True},
            "networks": [{"name": "private_network", "options": {"ip": "10.0.0.2"}}],
            "instance_raw_config_args": None,
            "provider": "virtualbox",
            "provider_options": {"gui": True},
            "provider_raw_config_args": None,
            "provider_override_args": None,
            "memory": 512,
            "cpus": 2,
        },
        {
            "name": "db",
            "hostname": "db",
            "box": "debian/bookworm64",
            "box_version": None,
            "box_url": None,
            "box_architecture": None,
            "box_download_checksum": None,
            "box_download_checksum_type": None,
            "config_options": {"synced_folder": False, "ssh.insert_key": True},
            "networks": [],
            "instance_raw_config_args": None,
            "provider": "virtualbox",
            "provider_options": {},
            "provider_raw_config_args": None,
            "provider_override_args": None,
            "memory": 512,
            "cpus": 2,
        },
    ]

    client._write_vagrantfile()  # noqa: SLF001

    rendered = (tmp_path / "Vagrantfile").read_text()
    assert 'config.vm.define "web"' in rendered
    assert 'config.vm.define "db"' in rendered
    assert "virtualbox.gui = true" in rendered
    assert 'c.vm.network "private_network", ip: "10.0.0.2"' in rendered


class CallbackSentinel(Exception):
    """Stop execution after a fake Ansible callback captures its payload."""


def make_callback_module(*, force_stop=False):
    """Create a module double whose callbacks capture and then stop execution."""
    payloads = {"exit": [], "fail": []}

    def callback(kind, **payload):
        """Capture an Ansible callback payload and stop the module method."""
        payloads[kind].append(payload)
        raise CallbackSentinel

    module = SimpleNamespace(
        params={"instance_name": None, "force_stop": force_stop},
        exit_json=lambda **payload: callback("exit", **payload),
        fail_json=lambda **payload: callback("fail", **payload),
    )
    module.payloads = payloads
    return module


class RecordingVagrant:
    """Record lifecycle calls made by a Vagrant client."""

    def __init__(self):
        """Initialize an empty lifecycle call log."""
        self.calls = []

    def up(self, *, provision):
        """Record an up call and its provision setting."""
        self.calls.append(("up", provision))

    def halt(self, *, force):
        """Record a halt call and its force setting."""
        self.calls.append(("halt", force))

    def destroy(self):
        """Record a destroy call."""
        self.calls.append(("destroy",))


@pytest.mark.parametrize(("running", "changed"), [(2, False), (1, True)])
def test_vagrant_up_reports_state_change(tmp_path, running, changed):
    """Verify up reports whether all configured instances are already running."""
    module = make_callback_module()
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client.instances = [{"name": "web"}, {"name": "db"}]
    client.provision = True
    client._has_error = False  # noqa: SLF001
    client.result = {}
    client._running = lambda: running  # noqa: SLF001
    client._conf = list  # noqa: SLF001
    client._get_stdout_log = lambda: str(tmp_path / "vagrant.out")  # noqa: SLF001
    client._vagrant = RecordingVagrant()  # noqa: SLF001

    with pytest.raises(CallbackSentinel):
        client.up()

    assert module.payloads["exit"][0]["changed"] is changed
    assert client._vagrant.calls == ([] if not changed else [("up", True)])  # noqa: SLF001


def test_vagrant_halt_honors_force_stop_and_skips_empty_state():
    """Verify halt forwards force_stop and does nothing for stopped instances."""
    module = make_callback_module(force_stop=True)
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client._running = lambda: 1  # noqa: SLF001
    client._vagrant = RecordingVagrant()  # noqa: SLF001
    with pytest.raises(CallbackSentinel):
        client.halt()
    assert module.payloads["exit"][0] == {"changed": True}
    assert client._vagrant.calls == [("halt", True)]  # noqa: SLF001

    module = make_callback_module(force_stop=True)
    client._module = module  # noqa: SLF001
    client._running = lambda: 0  # noqa: SLF001
    with pytest.raises(CallbackSentinel):
        client.halt()
    assert module.payloads["exit"][0] == {"changed": False}
    assert client._vagrant.calls == [("halt", True)]  # noqa: SLF001


def test_vagrant_destroy_force_halts_then_destroys_existing_instances():
    """Verify forced destroy halts existing instances before destroying them."""
    module = make_callback_module(force_stop=True)
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client._created = lambda: 1  # noqa: SLF001
    client._vagrant = RecordingVagrant()  # noqa: SLF001

    with pytest.raises(CallbackSentinel):
        client.destroy()

    assert module.payloads["exit"][0] == {"changed": True}
    assert client._vagrant.calls == [("halt", True), ("destroy",)]  # noqa: SLF001


def test_vagrant_destroy_skips_empty_state_without_force_halt():
    """Verify destroy is unchanged and makes no calls when nothing exists."""
    module = make_callback_module(force_stop=True)
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client._created = lambda: 0  # noqa: SLF001
    client._vagrant = RecordingVagrant()  # noqa: SLF001

    with pytest.raises(CallbackSentinel):
        client.destroy()

    assert module.payloads["exit"][0] == {"changed": False}
    assert client._vagrant.calls == []  # noqa: SLF001


def test_vagrant_destroy_without_force_stop_only_destroys_existing_instances():
    """Verify unforced destroy skips halting while removing existing instances."""
    module = make_callback_module(force_stop=False)
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client._created = lambda: 1  # noqa: SLF001
    client._vagrant = RecordingVagrant()  # noqa: SLF001

    with pytest.raises(CallbackSentinel):
        client.destroy()

    assert module.payloads["exit"][0] == {"changed": True}
    assert client._vagrant.calls == [("destroy",)]  # noqa: SLF001


def test_write_configs_reports_vagrantfile_validation_failure(tmp_path):
    """Verify Vagrantfile validation failures use the existing Ansible message."""
    module = make_callback_module()
    client = object.__new__(VagrantClient)
    client._module = module  # noqa: SLF001
    client._config = {"workdir": str(tmp_path)}  # noqa: SLF001
    client._write_vagrantfile = lambda: None  # noqa: SLF001

    class InvalidVagrant:
        """Raise the provider validation error expected by the module."""

        def validate(self, _workdir):
            """Raise a validation failure without invoking Vagrant."""
            raise subprocess.CalledProcessError(1, "vagrant validate", stderr="invalid")

    client._vagrant = InvalidVagrant()  # noqa: SLF001

    with pytest.raises(CallbackSentinel):
        client._write_configs()  # noqa: SLF001

    assert module.payloads["fail"][0] == {
        "msg": "Failed to validate generated Vagrantfile: invalid",
    }
