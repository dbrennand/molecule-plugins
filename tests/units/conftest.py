"""Shared fixtures for driver unit tests."""

import json
from pathlib import Path
from typing import Any

import pytest
from molecule import api


@pytest.fixture(scope="session")
def registered_drivers():
    """Return Molecule's registered driver mapping."""
    return api.drivers()


@pytest.fixture
def schema_path_for(registered_drivers):
    """Return a lookup for a registered driver's JSON schema path."""

    def lookup(driver_name: str) -> Path:
        schema_path_value = registered_drivers[driver_name].schema_file()
        assert schema_path_value is not None
        return Path(schema_path_value)

    return lookup


@pytest.fixture
def schema_for(schema_path_for):
    """Return a loader for a registered driver's JSON schema."""

    def load(driver_name: str) -> dict[str, Any]:
        return json.loads(schema_path_for(driver_name).read_text())

    return load
