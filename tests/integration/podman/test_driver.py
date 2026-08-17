"""Integration tests for the Podman driver."""

from pathlib import Path

import pytest

from molecule_plugins.podman import __file__ as podman_module_file

pytestmark = [pytest.mark.integration, pytest.mark.podman]


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the packaged Podman scenario template."""
    assert render_and_lint_template("podman").name == "default"


@pytest.mark.runtime
def test_podman_scenario(require_command_success, molecule_scenario):
    """Run the checked-in Podman scenario."""
    require_command_success(["podman", "info"])

    molecule_scenario("podman", "default")


@pytest.mark.runtime
def test_embedded_dockerfile_builds(require_command_success, run_command):
    """Build the driver's embedded Dockerfile through its validation playbook."""
    require_command_success(["podman", "info"])
    module_path = Path(podman_module_file).parent

    run_command(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            "playbooks/validate-dockerfile.yml",
        ],
        cwd=module_path,
        env={"ANSIBLE_FORCE_COLOR": "0"},
        timeout=1200,
    )
