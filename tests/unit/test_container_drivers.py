"""Unit tests for container drivers and local prerequisites."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.version import Version

from molecule.api import MoleculeRuntimeWarning
from molecule_plugins.containers.driver import Container, DriverBackend
from molecule_plugins.docker import driver as docker_driver
from molecule_plugins.openstack import driver as openstack_driver
from molecule_plugins.podman import driver as podman_driver
from molecule_plugins.vagrant.driver import Vagrant

vagrant_driver = sys.modules[Vagrant.__module__]


class ExitCalled(RuntimeError):
    """Raised by a fake Molecule exit helper."""


def raise_exit(message, **_kwargs):
    """Replace Molecule's process exit with an assertion-friendly exception."""
    error = ExitCalled(message)
    raise error


def test_docker_connection_options_and_resources(make_config, monkeypatch):
    driver = docker_driver.Docker(make_config())

    assert "docker exec" in driver.login_cmd_template
    assert driver.login_options("node") == {"instance": "node"}
    assert driver.ansible_connection_options("node") == {
        "ansible_connection": "community.docker.docker",
    }

    monkeypatch.setenv("DOCKER_HOST", "tcp://docker.example:2376")
    assert driver.ansible_connection_options("node") == {
        "ansible_connection": "community.docker.docker",
        "ansible_docker_extra_args": "-H=tcp://docker.example:2376",
    }
    assert driver.required_collections == {
        "ansible.posix": "1.4.0",
        "community.docker": "3.10.2",
    }
    schema_file = driver.schema_file()
    assert schema_file is not None
    assert Path(schema_file).is_file()


def test_docker_sanity_checks_daemon_once(make_config, monkeypatch):
    calls = []
    client = SimpleNamespace(ping=lambda: calls.append("ping"))
    fake_docker = SimpleNamespace(
        errors=SimpleNamespace(DockerException=RuntimeError),
        from_env=lambda: client,
    )
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    docker_driver.Docker._passed_sanity = False  # noqa: SLF001
    driver = docker_driver.Docker(make_config())

    driver.sanity_checks()
    driver.sanity_checks()

    assert calls == ["ping"]


def test_docker_sanity_reports_daemon_failure(make_config, monkeypatch):
    def from_env():
        error = RuntimeError("offline")
        raise error

    fake_docker = SimpleNamespace(
        errors=SimpleNamespace(DockerException=RuntimeError),
        from_env=from_env,
    )
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    monkeypatch.setattr(docker_driver, "sysexit_with_message", raise_exit)
    docker_driver.Docker._passed_sanity = False  # noqa: SLF001

    with pytest.raises(ExitCalled, match="Unable to contact the Docker daemon"):
        docker_driver.Docker(make_config()).sanity_checks()


def test_docker_reset_removes_owned_resources(make_config, monkeypatch):
    container_list_calls = []
    container_prune_calls = []
    network_list_calls = []
    stopped = []
    removed = []
    container = SimpleNamespace(id="container-1", stop=lambda **kwargs: stopped.append(kwargs))
    network = SimpleNamespace(name="network-1", remove=lambda: removed.append("network-1"))
    containers = SimpleNamespace(
        list=lambda **kwargs: container_list_calls.append(kwargs) or [container],
        prune=lambda **kwargs: container_prune_calls.append(kwargs)
        or {"ContainersDeleted": ["container-1"]},
    )
    networks = SimpleNamespace(
        list=lambda **kwargs: network_list_calls.append(kwargs) or [network],
    )
    fake_docker = SimpleNamespace(
        from_env=lambda: SimpleNamespace(containers=containers, networks=networks),
    )
    monkeypatch.setitem(sys.modules, "docker", fake_docker)

    docker_driver.Docker(make_config()).reset()

    owned_filter = {"filters": {"label": "owner=molecule"}}
    assert container_list_calls == [owned_filter]
    assert container_prune_calls == [owned_filter]
    assert network_list_calls == [owned_filter]
    assert stopped == [{"timeout": 3}]
    assert removed == ["network-1"]


def test_podman_command_and_connection_options(make_config, monkeypatch):
    monkeypatch.setenv("MOLECULE_PODMAN_EXECUTABLE", "podman-remote")
    monkeypatch.setattr(podman_driver, "which", lambda executable: f"/usr/bin/{executable}")
    driver = podman_driver.Podman(make_config())

    assert driver.podman_cmd == "/usr/bin/podman-remote"
    assert driver.login_cmd_template.startswith("/usr/bin/podman-remote exec")
    assert driver.login_options("node") == {"instance": "node"}
    assert driver.ansible_connection_options("node") == {
        "ansible_connection": "podman",
        "ansible_podman_executable": "podman-remote",
    }
    assert driver.required_collections == {"containers.podman": "1.8.1"}
    schema_file = driver.schema_file()
    assert schema_file is not None
    assert Path(schema_file).is_file()


def test_podman_command_reports_missing_executable(make_config, monkeypatch):
    monkeypatch.setattr(podman_driver, "which", lambda _executable: None)
    monkeypatch.setattr(podman_driver.util, "sysexit_with_message", raise_exit)

    with pytest.raises(ExitCalled, match="command not found in PATH podman"):
        _ = podman_driver.Podman(make_config()).podman_cmd


@pytest.mark.parametrize(
    ("version", "pipelining", "warning", "error"),
    [
        pytest.param("2.11.0", False, False, False, id="supported"),
        pytest.param("2.9.0", False, True, False, id="old-warning"),
        pytest.param("2.9.0", True, False, True, id="old-pipelining"),
    ],
)
def test_podman_sanity_compatibility(
    make_config,
    monkeypatch,
    version,
    pipelining,
    warning,
    error,
):
    runtime = SimpleNamespace(
        config=SimpleNamespace(ansible_pipelining=pipelining),
        version=Version(version),
    )
    monkeypatch.setattr(podman_driver, "Runtime", lambda: runtime)
    monkeypatch.setattr(podman_driver, "sysexit_with_message", raise_exit)
    driver = podman_driver.Podman(make_config())

    if warning:
        with pytest.warns(MoleculeRuntimeWarning):
            driver.sanity_checks()
    elif error:
        with pytest.raises(ExitCalled, match="pipelining is enabled"):
            driver.sanity_checks()
    else:
        driver.sanity_checks()
        assert driver._sanity_passed is True  # noqa: SLF001


def test_podman_reset_removes_owned_containers(make_config, monkeypatch):
    commands = []
    app = SimpleNamespace(run_command=lambda command: commands.append(command))
    monkeypatch.setattr(podman_driver, "which", lambda _executable: "/usr/bin/podman")
    monkeypatch.setattr(podman_driver, "get_app", lambda _path: app)

    podman_driver.Podman(make_config()).reset()

    assert commands == [
        ["podman", "rm", "--force", "--filter=label=owner=molecule"],
    ]


def test_podman_reset_skips_missing_executable(make_config, monkeypatch):
    monkeypatch.setattr(podman_driver, "which", lambda _executable: None)
    monkeypatch.setattr(
        podman_driver,
        "get_app",
        lambda _path: pytest.fail("get_app must not be called"),
    )

    podman_driver.Podman(make_config()).reset()


def test_containers_uses_selected_backend_resources(make_config):
    driver = Container(make_config())

    assert driver.name == "containers"
    assert isinstance(driver, DriverBackend)
    assert Path(driver._path).name in {"docker", "podman"}  # noqa: SLF001
    assert driver.required_collections == {
        "ansible.posix": "1.4.0",
        "community.docker": "3.10.2",
        "containers.podman": "1.8.1",
    }
    schema_file = driver.schema_file()
    assert schema_file is not None
    assert Path(schema_file).parent.name == "schema"
    assert Path(schema_file).parent.parent.name == "containers"


@pytest.mark.parametrize(
    ("backend", "expected_base"),
    [
        pytest.param("docker", "Docker", id="docker"),
        pytest.param("podman", "Podman", id="podman"),
    ],
)
def test_containers_selects_requested_backend(tmp_path, backend, expected_base):
    executable = tmp_path / backend
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    env = os.environ.copy()
    env["MOLECULE_CONTAINERS_BACKEND"] = backend
    env["PATH"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from molecule_plugins.containers.driver import Container; "
            "print(Container.__mro__[1].__name__)",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.strip() == expected_base


def test_containers_rejects_unsupported_backend(tmp_path):
    executable = tmp_path / "unsupported"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    env = os.environ.copy()
    env["MOLECULE_CONTAINERS_BACKEND"] = "unsupported"
    env["PATH"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", "import molecule_plugins.containers.driver"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "Driver unsupported is not supported" in result.stdout + result.stderr


def test_openstack_sanity_checks_dependency(make_config, monkeypatch):
    driver = openstack_driver.Openstack(make_config())
    monkeypatch.setattr(driver, "_is_module_installed", lambda _module: True)
    driver.sanity_checks()

    monkeypatch.setattr(driver, "_is_module_installed", lambda _module: False)
    monkeypatch.setattr(openstack_driver.util, "sysexit_with_message", raise_exit)
    with pytest.raises(ExitCalled, match="openstacksdk"):
        driver.sanity_checks()


def test_vagrant_sanity_checks_executable(make_config, monkeypatch):
    driver = vagrant_driver.Vagrant(make_config())
    monkeypatch.setattr(vagrant_driver, "which", lambda _executable: "/usr/bin/vagrant")
    driver.sanity_checks()

    monkeypatch.setattr(vagrant_driver, "which", lambda _executable: None)
    monkeypatch.setattr(vagrant_driver.util, "sysexit_with_message", raise_exit)
    with pytest.raises(ExitCalled, match="vagrant executable"):
        driver.sanity_checks()
