"""Integration tests for the OpenStack driver."""

import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.openstack]


def _openstack_credentials_available() -> bool:
    """Return whether clouds.yaml or explicit OpenStack auth is selected."""
    return bool(os.environ.get("OS_CLOUD") or os.environ.get("OS_AUTH_URL"))


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the import-resolved OpenStack scenario template."""
    assert render_and_lint_template("openstack").name == "default"


@pytest.mark.provider
def test_openstack_default_scenario(
    require_capability,
    require_provider_preflight,
    rendered_molecule_scenario,
):
    """Render the OpenStack template into the scenario and run the driver."""
    require_capability(
        _openstack_credentials_available(),
        "OS_CLOUD or OS_AUTH_URL is required for OpenStack integration",
    )
    preflight = [
        "ansible",
        "localhost",
        "--inventory",
        "localhost,",
        "--connection",
        "local",
        "--module-name",
        "openstack.cloud.server_info",
    ]
    if cloud := os.environ.get("OS_CLOUD"):
        preflight.extend(["--args", f"cloud={cloud}"])
    require_provider_preflight(preflight, provider="OpenStack")

    rendered_molecule_scenario("openstack", "default", redact_output=True)


@pytest.mark.provider
@pytest.mark.parametrize(
    "scenario_name",
    ["multiple", "network", "security_group", "volume"],
)
def test_openstack_scenario(
    scenario_name,
    require_capability,
    require_provider_preflight,
    molecule_scenario,
):
    """Run a checked-in OpenStack provider scenario."""
    require_capability(
        _openstack_credentials_available(),
        "OS_CLOUD or OS_AUTH_URL is required for OpenStack integration",
    )
    preflight = [
        "ansible",
        "localhost",
        "--inventory",
        "localhost,",
        "--connection",
        "local",
        "--module-name",
        "openstack.cloud.server_info",
    ]
    if cloud := os.environ.get("OS_CLOUD"):
        preflight.extend(["--args", f"cloud={cloud}"])
    require_provider_preflight(preflight, provider="OpenStack")

    molecule_scenario("openstack", scenario_name, redact_output=True)
