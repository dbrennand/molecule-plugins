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
from molecule.api import Driver
from molecule.config import Config

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
PLAYBOOKS = sorted(PACKAGE_ROOT.glob("*/playbooks/**/*.yml"))


def test_resource_inventory_is_complete():
    """Verify all expected packaged resource groups are present."""
    assert len(COOKIECUTTER_ROOTS) == 8
    assert {path.parents[1].name for path in COOKIECUTTER_ROOTS} == DRIVER_NAMES
    assert len(PLAYBOOKS) == 21


def test_package_registers_all_molecule_drivers():
    """Verify the package registers every expected Molecule driver."""
    plugins = {
        plugin.name: plugin
        for plugin in entry_points(group="molecule.driver")
        if plugin.value.startswith("molecule_plugins.")
    }

    assert set(plugins) == DRIVER_NAMES
    for plugin in plugins.values():
        assert issubclass(plugin.load(), Driver)


def test_molecule_cli_lists_all_project_drivers():
    """Verify the Molecule CLI lists every project driver."""
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
    """Verify cookiecutter templates render and their YAML parses."""
    rendered_files = render_cookiecutter_tree(config_file, tmp_path)
    yaml_files = [path for path in rendered_files if path.suffix in {".yml", ".yaml"}]

    assert rendered_files
    assert yaml_files
    assert any(path.name == "converge.yml" for path in yaml_files)
    for path in rendered_files:
        assert "cookiecutter." not in path.read_text(encoding="utf-8")
    for path in yaml_files:
        assert DataLoader().load(path.read_text(encoding="utf-8")) is not None


def test_molecule_config_substitutes_environment_values(monkeypatch, tmp_path):
    """Verify explicit substitutions override defaults without contacting Docker."""
    molecule_file = tmp_path / "molecule.yml"
    molecule_file.write_text(
        """---
 driver:
   name: docker
 platforms:
   - name: ${MOLECULE_TEST_NAME:-instance-local}
     image: ${MOLECULE_TEST_IMAGE:-docker.io/library/python:3.12-slim}
 provisioner:
   name: ansible
 """,
        encoding="utf-8",
    )
    monkeypatch.setenv("MOLECULE_TEST_NAME", "instance-explicit")
    monkeypatch.delenv("MOLECULE_TEST_IMAGE", raising=False)

    config = Config(str(molecule_file))
    config_data = vars(config).get("config_data", vars(config).get("config"))

    assert config_data is not None
    assert config_data["platforms"][0]["name"] == "instance-explicit"
    assert config_data["platforms"][0]["image"] == "docker.io/library/python:3.12-slim"


@pytest.mark.parametrize(
    "playbook", PLAYBOOKS, ids=lambda path: str(path.relative_to(PACKAGE_ROOT))
)
def test_packaged_playbooks_parse_with_ansible(playbook):
    """Verify packaged playbooks parse through Ansible's loader."""
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
    """Verify packaged Python resources compile successfully."""
    py_compile.compile(
        str(source),
        cfile=str(tmp_path / f"{source.stem}.pyc"),
        doraise=True,
    )
