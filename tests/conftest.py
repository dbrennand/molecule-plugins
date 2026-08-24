"""Shared fixtures for the clean-room pytest suite."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def make_config(tmp_path):
    """Build the smallest configuration object required by the drivers."""

    def _make_config(*, command_args=None, platforms=None, config_data=None):
        ephemeral_directory = str(tmp_path / "ephemeral")
        driver_data = {
            "name": "unused",
            "options": {"managed": True},
            "safe_files": [],
            "ssh_connection_options": [],
        }
        if config_data:
            driver_data.update(config_data.get("driver", {}))

        return SimpleNamespace(
            command_args=command_args or {},
            config={"platforms": platforms or []},
            config_data={"driver": driver_data},
            driver=SimpleNamespace(
                instance_config=str(tmp_path / "instance_config.yml"),
            ),
            platforms=SimpleNamespace(instances=platforms or []),
            provisioner=SimpleNamespace(
                inventory_directory=str(tmp_path / "inventory"),
                inventory_file=str(tmp_path / "inventory" / "hosts.yml"),
                name="ansible",
            ),
            scenario=SimpleNamespace(
                ephemeral_directory=ephemeral_directory,
                name="default",
            ),
            state=SimpleNamespace(created=False, converged=False),
        )

    return _make_config
