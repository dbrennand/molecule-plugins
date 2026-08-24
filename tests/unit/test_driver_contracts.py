"""Shared contracts for SSH-oriented Molecule drivers."""

from pathlib import Path

import pytest
from molecule import util

from molecule_plugins.azure.driver import Azure
from molecule_plugins.ec2.driver import EC2
from molecule_plugins.gce.driver import GCE
from molecule_plugins.openstack.driver import Openstack
from molecule_plugins.vagrant.driver import Vagrant


DRIVERS = [
    pytest.param(Azure, "azure", id="azure"),
    pytest.param(EC2, "ec2", id="ec2"),
    pytest.param(GCE, "gce", id="gce"),
    pytest.param(Openstack, "openstack", id="openstack"),
    pytest.param(Vagrant, "vagrant", id="vagrant"),
]


@pytest.mark.parametrize(("driver_class", "expected_name"), DRIVERS)
def test_ssh_driver_metadata_and_templates(
    make_config,
    driver_class,
    expected_name,
):
    config = make_config(
        command_args={"host": "node"},
        config_data={"driver": {"ssh_connection_options": ["-o TestOption=yes"]}},
    )
    driver = driver_class(config)

    assert driver.name == expected_name
    assert Path(driver.template_dir()).is_dir()
    assert (Path(driver.template_dir()) / "cookiecutter.json").is_file()
    assert "{address}" in driver.login_cmd_template
    assert "{user}" in driver.login_cmd_template
    assert "{port}" in driver.login_cmd_template
    assert "{identity_file}" in driver.login_cmd_template
    assert "-o TestOption=yes" in driver.login_cmd_template
    assert driver.instance_config in driver.default_safe_files


@pytest.mark.parametrize(("driver_class", "expected_name"), DRIVERS)
def test_ssh_driver_reads_linux_instance_config(
    make_config,
    monkeypatch,
    driver_class,
    expected_name,
):
    instance = {
        "address": "192.0.2.10",
        "identity_file": "/tmp/id_test",
        "instance": "node",
        "instance_os_type": "linux",
        "port": 2222,
        "user": "tester",
    }
    monkeypatch.setattr(util, "safe_load_file", lambda _path: [instance])
    driver = driver_class(make_config())

    assert driver.login_options("node")["instance"] == "node"
    assert driver.ansible_connection_options("node") == {
        "ansible_connection": "ssh",
        "ansible_host": "192.0.2.10",
        "ansible_port": 2222,
        "ansible_private_key_file": "/tmp/id_test",
        "ansible_ssh_common_args": " ".join(driver.ssh_connection_options),
        "ansible_user": "tester",
    }
    assert driver.name == expected_name


@pytest.mark.parametrize(("driver_class", "expected_name"), DRIVERS)
@pytest.mark.parametrize("error", [StopIteration, OSError])
def test_ssh_driver_returns_no_connection_before_provisioning(
    make_config,
    monkeypatch,
    driver_class,
    expected_name,
    error,
):
    driver = driver_class(make_config())

    def fail(_instance_name):
        raise error

    monkeypatch.setattr(driver, "_get_instance_config", fail)

    assert driver.ansible_connection_options("missing") == {}
    assert driver.name == expected_name


def test_gce_builds_windows_connection(make_config, monkeypatch):
    instance = {
        "address": "192.0.2.20",
        "instance": "windows",
        "instance_os_type": "windows",
        "password": "secret",
        "port": 5986,
        "user": "Administrator",
        "winrm_server_cert_validation": "ignore",
        "winrm_transport": "ntlm",
    }
    monkeypatch.setattr(util, "safe_load_file", lambda _path: [instance])

    assert GCE(make_config()).ansible_connection_options("windows") == {
        "ansible_become_method": "runas",
        "ansible_connection": "winrm",
        "ansible_host": "192.0.2.20",
        "ansible_password": "secret",
        "ansible_port": 5986,
        "ansible_user": "Administrator",
        "ansible_winrm_server_cert_validation": "ignore",
        "ansible_winrm_transport": "ntlm",
    }


def test_ec2_applies_platform_overrides_and_fetches_password(
    make_config,
    monkeypatch,
):
    instance = {
        "address": "192.0.2.30",
        "identity_file": "/tmp/id_test",
        "instance": "windows",
        "instance_ids": ["i-123"],
        "port": 22,
        "user": "ec2-user",
    }
    platforms = [
        {
            "connection_options": {
                "ansible_connection": "winrm",
                "ansible_port": 5986,
                "ansible_user": "Administrator",
            },
            "name": "windows",
        },
    ]
    monkeypatch.setattr(util, "safe_load_file", lambda _path: [instance])
    driver = EC2(make_config(platforms=platforms))
    monkeypatch.setattr(driver, "_get_windows_instance_pass", lambda *_args: "secret")

    options = driver.ansible_connection_options("windows")

    assert options["ansible_connection"] == "winrm"
    assert options["ansible_password"] == "secret"
    assert options["ansible_port"] == 5986
    assert options["ansible_user"] == "Administrator"


@pytest.mark.parametrize(
    ("command_args", "platforms", "expected_host"),
    [
        pytest.param({"host": "explicit"}, [{"name": "other"}], "explicit", id="host"),
        pytest.param({}, [{"name": "single"}], "single", id="single-platform"),
    ],
)
def test_ec2_login_selects_host(
    make_config,
    monkeypatch,
    command_args,
    platforms,
    expected_host,
):
    selected = []
    driver = EC2(make_config(command_args=command_args, platforms=platforms))

    def connection_options(host):
        selected.append(host)
        return {"ansible_connection": "ssh"}

    monkeypatch.setattr(driver, "ansible_connection_options", connection_options)

    assert driver.login_cmd_template.startswith("ssh ")
    assert selected == [expected_host]


def test_ec2_login_rejects_ambiguous_host(make_config):
    driver = EC2(make_config(platforms=[{"name": "one"}, {"name": "two"}]))

    with pytest.raises(SystemExit, match="1"):
        _ = driver.login_cmd_template
