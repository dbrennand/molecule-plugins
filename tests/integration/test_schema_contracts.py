"""Integration tests for Molecule driver schema contracts."""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validators

from molecule_plugins import __file__ as molecule_plugins_file

SCHEMA_ROOT = Path(molecule_plugins_file).parent
SCHEMA_FILES = tuple(
    sorted(
        SCHEMA_ROOT.joinpath(driver, "schema", "driver.json")
        for driver in ("containers", "docker", "podman")
    )
)


def _load_schema(schema_file):
    """Load a driver schema from the installed package."""
    return json.loads(schema_file.read_text(encoding="utf-8"))


def _supported_names(schema):
    """Return all driver names accepted by a schema."""
    return tuple(schema["$defs"]["MoleculeDriverModel"]["properties"]["name"]["enum"])


def _document(driver_name, platform=None):
    """Build a schema document containing a driver and platform list."""
    return {"driver": {"name": driver_name}, "platforms": [platform or {"name": "instance"}]}


SCHEMA_CASES = tuple(
    pytest.param(schema_file, _load_schema(schema_file), id=schema_file.parent.parent.name)
    for schema_file in SCHEMA_FILES
)
SUPPORTED_NAME_CASES = tuple(
    pytest.param(schema_file, driver_name, id=f"{schema_file.parent.parent.name}-{driver_name}")
    for schema_file in SCHEMA_FILES
    for driver_name in _supported_names(_load_schema(schema_file))
)
UNSUPPORTED_NAME_CASES = tuple(
    pytest.param(schema_file, id=schema_file.parent.parent.name)
    for schema_file in SCHEMA_FILES
)


@pytest.mark.parametrize(("schema_file", "schema"), SCHEMA_CASES)
def test_driver_schemas_are_valid_meta_schemas(schema_file, schema):
    """Verify each checked-in driver schema passes its declared meta-schema."""
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)


@pytest.mark.parametrize(("schema_file", "driver_name"), SUPPORTED_NAME_CASES)
def test_driver_schemas_accept_supported_names_with_platforms(schema_file, driver_name):
    """Verify every schema-supported driver name accepts a complete document."""
    schema = _load_schema(schema_file)
    validator = validators.validator_for(schema)(schema)
    validator.validate(_document(driver_name))


@pytest.mark.parametrize("schema_file", UNSUPPORTED_NAME_CASES)
def test_driver_schemas_reject_unsupported_names_with_platforms(schema_file):
    """Verify each schema rejects an unsupported name in a complete document."""
    schema = _load_schema(schema_file)
    validator = validators.validator_for(schema)(schema)
    with pytest.raises(ValidationError):
        validator.validate(_document("unsupported"))


@pytest.mark.parametrize(
    ("schema_file", "document"),
    [
        pytest.param(
            SCHEMA_ROOT / "docker/schema/driver.json",
            _document("docker", {"name": "docker-representative", "cgroupns_mode": "private", "shm_size": "64M", "docker_networks": [{"name": "molecule"}], "restart_policy": "unless-stopped"}),
            id="docker-representative",
        ),
        pytest.param(
            SCHEMA_ROOT / "podman/schema/driver.json",
            _document("podman", {"name": "podman-representative", "rootless": True, "cgroup_manager": "systemd", "systemd": "always", "extra_opts": ["--log-level=debug"]}),
            id="podman-representative",
        ),
        pytest.param(
            SCHEMA_ROOT / "containers/schema/driver.json",
            _document("containers", {"name": "containers-portable", "command": "sleep infinity", "restart_policy": "on-failure", "registry": {"credentials": {"username": "user", "password": "secret"}}}),
            id="containers-portable",
        ),
    ],
)
def test_driver_schemas_accept_representative_platforms(schema_file, document):
    """Verify each driver's representative platform options are accepted."""
    schema = _load_schema(schema_file)
    validator = validators.validator_for(schema)(schema)
    validator.validate(document)


@pytest.mark.parametrize(
    ("schema_file", "document"),
    [
        pytest.param(SCHEMA_ROOT / "docker/schema/driver.json", _document("docker", {"name": "docker-invalid", "systemd": "always"}), id="docker-rejects-podman-systemd"),
        pytest.param(SCHEMA_ROOT / "podman/schema/driver.json", _document("podman", {"name": "podman-invalid", "docker_networks": []}), id="podman-rejects-docker-networks"),
        pytest.param(SCHEMA_ROOT / "containers/schema/driver.json", _document("containers", {"name": "containers-invalid", "docker_networks": []}), id="containers-rejects-docker-networks"),
        pytest.param(SCHEMA_ROOT / "containers/schema/driver.json", _document("containers", {"name": "containers-invalid", "systemd": "always"}), id="containers-rejects-podman-systemd"),
        pytest.param(SCHEMA_ROOT / "containers/schema/driver.json", _document("containers", {"name": "containers-invalid", "command": ["sleep", "infinity"]}), id="containers-rejects-list-command"),
        pytest.param(SCHEMA_ROOT / "containers/schema/driver.json", _document("containers", {"name": "containers-invalid", "restart_policy": "unless-stopped"}), id="containers-rejects-unless-stopped"),
    ],
)
def test_driver_schemas_reject_driver_specific_invalid_platforms(schema_file, document):
    """Verify driver schemas reject options owned by another backend."""
    schema = _load_schema(schema_file)
    validator = validators.validator_for(schema)(schema)
    with pytest.raises(ValidationError):
        validator.validate(document)
