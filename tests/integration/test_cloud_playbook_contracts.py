"""Offline contracts for cloud and Vagrant playbook resources."""

from pathlib import Path

from ansible.parsing.dataloader import DataLoader
from jinja2 import Template

import molecule_plugins

PACKAGE_ROOT = Path(molecule_plugins.__file__).parent


def _resource(provider, *parts):
    """Return a packaged playbook resource path."""
    return PACKAGE_ROOT.joinpath(provider, *parts)


def _load_yaml(path, *, render_outer=False):
    """Load a playbook after optionally rendering its Cookiecutter layer."""
    source = path.read_text()
    if render_outer:
        source = Template(source).render()
    return DataLoader().load(source)


def _mappings_with_keys(value, keys):
    """Find nested mappings containing every key in ``keys``."""
    found = []
    if isinstance(value, dict):
        if set(keys).issubset(value):
            found.append(value)
        for child in value.values():
            found.extend(_mappings_with_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(_mappings_with_keys(child, keys))
    return found


def _first_mapping(document, keys):
    """Return the first nested mapping containing the requested keys."""
    matches = _mappings_with_keys(document, keys)
    assert matches, f"no mapping contains {keys}"
    return matches[0]


def test_azure_playbooks_emit_instance_config_and_pair_resource_group():
    """Verify Azure emits connection data and destroys the molecule group."""
    create = _load_yaml(
        _resource(
            "azure",
            "cookiecutter",
            "{{cookiecutter.molecule_directory}}",
            "{{cookiecutter.scenario_name}}",
            "create.yml",
        ),
        render_outer=True,
    )
    destroy = _load_yaml(
        _resource(
            "azure",
            "cookiecutter",
            "{{cookiecutter.molecule_directory}}",
            "{{cookiecutter.scenario_name}}",
            "destroy.yml",
        ),
        render_outer=True,
    )
    instance = _first_mapping(create, {"instance", "address", "user", "port", "identity_file"})
    assert set(instance) >= {"instance", "address", "user", "port", "identity_file"}
    assert "resource_group_name: molecule" in _resource(
        "azure", "cookiecutter", "{{cookiecutter.molecule_directory}}", "{{cookiecutter.scenario_name}}", "create.yml"
    ).read_text()
    assert "resource_group_name: molecule" in _resource(
        "azure", "cookiecutter", "{{cookiecutter.molecule_directory}}", "{{cookiecutter.scenario_name}}", "destroy.yml"
    ).read_text()
    assert _first_mapping(destroy, {"instance_conf"})["instance_conf"] == {}


def test_ec2_playbooks_persist_run_and_instance_config_contracts():
    """Verify EC2 persists run identity and instance IDs for cleanup."""
    create_path = _resource(
        "ec2", "cookiecutter", "{{cookiecutter.molecule_directory}}", "{{cookiecutter.scenario_name}}", "create.yml"
    )
    destroy_path = _resource(
        "ec2", "cookiecutter", "{{cookiecutter.molecule_directory}}", "{{cookiecutter.scenario_name}}", "destroy.yml"
    )
    create = _load_yaml(create_path, render_outer=True)
    instance = _first_mapping(
        create, {"instance", "address", "user", "port", "identity_file", "instance_ids"}
    )
    assert {"instance", "address", "user", "port", "identity_file"} <= set(instance)
    assert "instance_ids" in instance
    create_text = create_path.read_text()
    destroy_text = destroy_path.read_text()
    assert "run_id" in create_text
    assert "run_id" in destroy_text
    run_config_path = "lookup('env', 'MOLECULE_EPHEMERAL_DIRECTORY') }}/run-config.yml"
    assert run_config_path in create_text
    assert run_config_path in destroy_text
    assert "map(attribute='instance_ids')" in destroy_text
    assert "molecule_instance_config" in create_text
    assert "molecule_instance_config" in destroy_text


def test_gce_handlers_keep_linux_and_windows_connection_contracts():
    """Verify GCE handlers emit distinct SSH and WinRM instance data."""
    handlers = _load_yaml(_resource("gce", "playbooks", "handlers", "main.yml"))
    linux_task = next(task for task in handlers if "Linux" in task["name"])
    windows_task = next(task for task in handlers if "Windows" in task["name"])
    linux = _first_mapping(linux_task, {"instance", "address", "user", "port", "identity_file"})
    windows = _first_mapping(windows_task, {"instance", "address", "user", "password", "port"})
    assert linux["instance_os_type"] == "{{ molecule_yml.driver.instance_os_type }}"
    assert windows["instance_os_type"] == "{{ molecule_yml.driver.instance_os_type }}"
    assert "identity_file" in linux
    assert {"password", "winrm_transport", "winrm_server_cert_validation"} <= windows.keys()
    create = _resource("gce", "playbooks", "create.yml").read_text()
    assert "include_tasks: tasks/create_linux_instance.yml" in create
    assert "include_tasks: tasks/create_windows_instance.yml" in create
    assert 'instance_os_type  | lower == "linux"' in create
    assert 'instance_os_type  | lower == "windows"' in create


def test_gce_create_destroy_pair_platform_identity_inputs():
    """Verify GCE uses platform names and matching project and zone inputs."""
    create = _resource("gce", "playbooks", "create.yml").read_text()
    destroy = _resource("gce", "playbooks", "destroy.yml").read_text()
    create_tasks = "\n".join(
        _resource("gce", "playbooks", "tasks", name).read_text()
        for name in ("create_linux_instance.yml", "create_windows_instance.yml")
    )
    assert 'loop: "{{ molecule_yml.platforms }}"' in create_tasks
    assert 'name: "{{ item.name }}"' in create_tasks
    assert 'name: "{{ item.name }}"' in destroy
    assert 'gcp_project_id: "{{ molecule_yml.driver.project_id' in create
    assert 'project: "{{ gcp_project_id }}"' in create_tasks
    assert 'project: "{{ molecule_yml.driver.project_id' in destroy
    assert "molecule_yml.driver.region + '-b'" in destroy


def test_openstack_address_selection_and_instance_config_contract():
    """Verify OpenStack address precedence and emitted connection fields."""
    path = _resource("openstack", "playbooks", "tasks", "server_addr.yml")
    source = path.read_text()
    document = _load_yaml(path)
    instance = _first_mapping(document, {"instance", "address", "user", "port", "identity_file"})
    assert set(instance) >= {"instance", "address", "user", "port", "identity_file"}
    assert source.index("item.access_ipv4") < source.index("item.access_ipv6")
    assert source.index("item.access_ipv6") < source.index("'floating'")
    assert "when: not address" in source
    assert "[0].addr" in source


def test_openstack_create_destroy_pair_uuid_resource_identity():
    """Verify OpenStack creates and destroys the same UUID-based server name."""
    create = _resource("openstack", "playbooks", "create.yml").read_text()
    destroy = _resource("openstack", "playbooks", "destroy.yml").read_text()
    token = "molecule-test-{{ item.name }}-{{ uuid }}"
    assert token in create
    assert token in destroy
    assert "server_info.servers" in create


def test_vagrant_create_maps_module_result_to_instance_config():
    """Verify Vagrant maps server result fields into Molecule instance data."""
    document = _load_yaml(_resource("vagrant", "playbooks", "create.yml"))
    instance = _first_mapping(document, {"instance", "address", "user", "port", "identity_file"})
    assert instance == {
        "instance": "{{ item.Host }}",
        "address": "{{ item.HostName }}",
        "user": "{{ item.User }}",
        "port": "{{ item.Port }}",
        "identity_file": "{{ item.IdentityFile }}",
    }
