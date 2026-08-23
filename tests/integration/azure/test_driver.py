"""Integration tests for the Azure driver."""

import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.azure]
AZURE_CREDENTIALS = (
    "AZURE_CLIENT_ID",
    "AZURE_SECRET",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_TENANT",
)


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the import-resolved Azure scenario template."""
    assert render_and_lint_template("azure").name == "default"


@pytest.mark.provider
@pytest.mark.parametrize(
    ("scenario_name", "render_files", "converge_overlay"),
    [
        ("default", ("converge.yml", "create.yml", "destroy.yml"), True),
        ("multi_node", ("create.yml", "destroy.yml"), False),
    ],
)
def test_azure_scenario(
    scenario_name,
    render_files,
    converge_overlay,
    require_capability,
    require_provider_preflight,
    rendered_molecule_scenario,
):
    """Render the Azure template into the scenario and run the driver."""
    missing = [name for name in AZURE_CREDENTIALS if not os.environ.get(name)]
    require_capability(not missing, f"Missing Azure credential variables: {missing}")
    require_provider_preflight(
        [
            "ansible",
            "localhost",
            "--inventory",
            "localhost,",
            "--connection",
            "local",
            "--module-name",
            "azure.azcollection.azure_rm_subscription_info",
        ],
        provider="Azure",
    )

    rendered_molecule_scenario(
        "azure",
        scenario_name,
        render_files=render_files,
        converge_overlay=converge_overlay,
        redact_output=True,
    )
