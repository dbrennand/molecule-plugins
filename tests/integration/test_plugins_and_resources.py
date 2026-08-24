"""Integration tests for installed plugins and packaged resources."""

import json
import py_compile
import shutil
import subprocess
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from ansible.parsing.dataloader import DataLoader
from jinja2 import Environment, StrictUndefined
from jsonschema import ValidationError, validators
from molecule.api import Driver

import molecule_plugins

pytestmark = pytest.mark.integration

PACKAGE_ROOT = Path(molecule_plugins.__file__).parent
DRIVER_NAMES = {
    "azure",
    "containers",
    "docker",
    "ec2",
    "gce",
    "openstack",
    "podman",
    "vagrant",
}
COOKIECUTTER_ROOTS = sorted(PACKAGE_ROOT.glob("*/cookiecutter/cookiecutter.json"))
SCHEMAS = [
    pytest.param(PACKAGE_ROOT / name / "schema" / "driver.json", name, id=name)
    for name in ("containers", "docker", "podman")
]
PLAYBOOKS = sorted(PACKAGE_ROOT.glob("*/playbooks/**/*.yml"))


def test_resource_inventory_is_complete():
    assert len(COOKIECUTTER_ROOTS) == 8
    assert {path.parents[1].name for path in COOKIECUTTER_ROOTS} == DRIVER_NAMES
    assert len(PLAYBOOKS) == 21


def test_package_registers_all_molecule_drivers():
    plugins = {
        plugin.name: plugin
        for plugin in entry_points(group="molecule.driver")
        if plugin.value.startswith("molecule_plugins.")
    }

    assert set(plugins) == DRIVER_NAMES
    for plugin in plugins.values():
        assert issubclass(plugin.load(), Driver)


def test_molecule_cli_lists_all_project_drivers():
    molecule = shutil.which("molecule")
    assert molecule is not None

    result = subprocess.run(
        [molecule, "drivers"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert set(result.stdout.splitlines()) >= DRIVER_NAMES


def render_cookiecutter_tree(config_file, destination):
    """Render the outer cookiecutter layer while preserving Ansible Jinja."""
    source_root = config_file.parent
    defaults = json.loads(config_file.read_text(encoding="utf-8"))
    context = {
        key: value if value != "OVERRIDDEN" else f"test_{key}"
        for key, value in defaults.items()
    }
    context.update(
        {
            "molecule_directory": "molecule",
            "role_name": "test_role",
            "scenario_name": "default",
        },
    )
    environment = Environment(
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    rendered_files = []

    for source in source_root.rglob("*"):
        if not source.is_file() or source == config_file:
            continue
        relative = source.relative_to(source_root)
        rendered_relative = Path(
            *[
                environment.from_string(part).render(cookiecutter=context)
                for part in relative.parts
            ],
        )
        target = destination / rendered_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = environment.from_string(source.read_text(encoding="utf-8")).render(
            cookiecutter=context,
        )
        target.write_text(rendered, encoding="utf-8")
        rendered_files.append(target)

    return rendered_files


@pytest.mark.parametrize(
    "config_file", COOKIECUTTER_ROOTS, ids=lambda path: path.parents[1].name
)
def test_cookiecutter_templates_render_and_parse(config_file, tmp_path):
    rendered_files = render_cookiecutter_tree(config_file, tmp_path)
    yaml_files = [path for path in rendered_files if path.suffix in {".yml", ".yaml"}]

    assert rendered_files
    assert yaml_files
    assert any(path.name == "converge.yml" for path in yaml_files)
    for path in rendered_files:
        assert "cookiecutter." not in path.read_text(encoding="utf-8")
    for path in yaml_files:
        assert DataLoader().load(path.read_text(encoding="utf-8")) is not None


@pytest.mark.parametrize(("schema_file", "driver_name"), SCHEMAS)
def test_driver_schemas_accept_only_supported_name(schema_file, driver_name):
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)

    validator.validate({"driver": {"name": driver_name}})
    with pytest.raises(ValidationError):
        validator.validate({"driver": {"name": "unsupported"}})


@pytest.mark.parametrize(
    "playbook", PLAYBOOKS, ids=lambda path: str(path.relative_to(PACKAGE_ROOT))
)
def test_packaged_playbooks_parse_with_ansible(playbook):
    assert DataLoader().load(playbook.read_text(encoding="utf-8")) is not None


@pytest.mark.parametrize(
    "source",
    [
        PACKAGE_ROOT
        / "docker"
        / "playbooks"
        / "filter_plugins"
        / "get_docker_networks.py",
        PACKAGE_ROOT / "gce" / "playbooks" / "files" / "windows_auth.py",
    ],
    ids=("docker-filter", "gce-windows-auth"),
)
def test_packaged_python_resources_compile(source, tmp_path):
    py_compile.compile(
        str(source),
        cfile=str(tmp_path / f"{source.stem}.pyc"),
        doraise=True,
    )
