"""Unit tests."""

import pytest
from jsonschema import Draft202012Validator, ValidationError, validate

from molecule_plugins.podman.driver import Podman


def test_podman_driver_is_detected(registered_drivers):
    """Asserts that molecule recognizes the driver."""
    assert "podman" in registered_drivers


def test_podman_driver_provides_schema(schema_path_for):
    """Asserts that the podman driver provides a JSON schema file."""
    schema_path = schema_path_for("podman")

    assert schema_path.is_file()
    assert schema_path.as_posix().endswith("podman/schema/driver.json")


def test_podman_driver_schema_is_valid(schema_for):
    """Asserts that the podman driver schema is a valid JSON Schema."""
    schema = schema_for("podman")
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("config", "valid"),
    [
        # Minimal valid configuration
        (
            {
                "driver": {"name": "podman"},
                "platforms": [{"name": "instance", "image": "image:tag"}],
            },
            True,
        ),
        # Comprehensive configuration exercising all documented options
        (
            {
                "driver": {"name": "podman"},
                "platforms": [
                    {
                        "buildargs": {"http_proxy": "http://proxy:8080/"},
                        "capabilities": ["SYS_ADMIN"],
                        "cert_path": "/foo/bar/cert.pem",
                        "cgroup_manager": "systemd",
                        "command": "sleep infinity",
                        "detach": True,
                        "devices": ["/dev/fuse:/dev/fuse:rwm"],
                        "dns_servers": ["8.8.8.8"],
                        "dockerfile": "Dockerfile.j2",
                        "env": {"FOO": "bar"},
                        "etc_hosts": {"host1.example.com": "10.3.1.5"},
                        "exposed_ports": ["53/udp"],
                        "extra_opts": ["--log-level=debug"],
                        "groups": ["webserver", "db"],
                        "hostname": "instance",
                        "image": "image:tag",
                        "ip": "10.10.99.10",
                        "name": "instance",
                        "network": "host",
                        "override_command": True,
                        "pid_mode": "host",
                        "pre_build_image": False,
                        "privileged": True,
                        "published_ports": ["0.0.0.0:8053:53/udp"],
                        "pull": True,
                        "registry": {
                            "credentials": {"password": "p", "username": "u"},
                            "url": "registry.example.com",
                        },
                        "restart_policy": "on-failure",
                        "restart_retries": 1,
                        "rootless": True,
                        "security_opts": ["seccomp=unconfined"],
                        "storage_opt": "overlay.mount_program=/usr/bin/fuse-overlayfs",
                        "systemd": "false",
                        "tls_verify": True,
                        "tmpfs": ["/tmp", "rw,size=787448k,mode=1777"],
                        "tty": True,
                        "ulimits": ["nofile:262144:262144"],
                        "volumes": ["/sys/fs/cgroup:/sys/fs/cgroup:ro"],
                    }
                ],
            },
            True,
        ),
        # Docker-only options must be rejected
        (
            {
                "driver": {"name": "podman"},
                "platforms": [
                    {
                        "name": "instance",
                        "image": "image:tag",
                        "docker_networks": [{"name": "foo"}],
                        "systemd": "true",
                    }
                ],
            },
            False,
        ),
    ],
)
def test_podman_driver_schema_validation(schema_for, config, valid):
    """Asserts that the podman driver schema accepts/rejects configs correctly."""
    schema = schema_for("podman")
    if valid:
        validate(instance=config, schema=schema)
    else:
        with pytest.raises(ValidationError):
            validate(instance=config, schema=schema)


def test_driver_initializes_without_podman_executable(monkeypatch):
    """Make sure we can initialize driver without having an executable present."""
    monkeypatch.setenv("MOLECULE_PODMAN_EXECUTABLE", "bad-executable")
    Podman()


def test_driver_resets_without_podman_executable(monkeypatch):
    """Make sure we can reset the driver without having an executable present."""
    monkeypatch.setenv("MOLECULE_PODMAN_EXECUTABLE", "bad-executable")
    podman_driver = Podman()
    podman_driver.reset()
