"""Integration tests for the Docker driver."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the packaged Docker scenario template."""
    assert render_and_lint_template("docker").name == "default"


@pytest.mark.runtime
@pytest.mark.parametrize("scenario_name", ["env_substitution", "with_context"])
def test_docker_scenario(scenario_name, require_command_success, molecule_scenario):
    """Run a checked-in Docker runtime scenario."""
    require_command_success(["docker", "info"])
    env = (
        {"MOLECULE_ROLE_IMAGE": "debian:bullseye"}
        if scenario_name == "env_substitution"
        else None
    )

    molecule_scenario("docker", scenario_name, env=env)
