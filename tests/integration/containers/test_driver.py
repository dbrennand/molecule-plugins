"""Integration tests for the Containers driver."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.containers]


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the import-resolved Containers scenario template."""
    assert render_and_lint_template("containers").name == "default"


@pytest.mark.runtime
def test_containers_scenario(require_container_runtime, rendered_molecule_scenario):
    """Render the Containers template and run the driver against a local runtime."""
    require_container_runtime()

    rendered_molecule_scenario("containers", "default")
