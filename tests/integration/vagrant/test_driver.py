"""Integration tests for the Vagrant driver."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.vagrant]
POSITIVE_SCENARIOS = [
    "box_url",
    "config_options",
    "default",
    "default_compat",
    "hostname",
    "network",
    "provider_config_options",
    "vagrant_root",
]
VAGRANT_XFAIL = {
    "box_url": (
        "The CentOS Stream 9 box fails to boot under nested KVM on "
        "GitHub-hosted runners with vagrant-libvirt 0.12.x"
    ),
    "network": (
        "vagrant-libvirt 0.12.x vagrant validate rejects the public_network "
        "configuration that upstream CI validated with older plugin releases"
    ),
}


def _scenario_param(scenario_name: str):
    """Mark environment-incompatible upstream scenarios as strict xfails."""
    reason = VAGRANT_XFAIL.get(scenario_name)
    if reason:
        return pytest.param(
            scenario_name, marks=pytest.mark.xfail(reason=reason, strict=True)
        )
    return pytest.param(scenario_name)


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the packaged Vagrant scenario template."""
    assert render_and_lint_template("vagrant").name == "default"


@pytest.mark.runtime
@pytest.mark.parametrize(
    "scenario_name", [_scenario_param(name) for name in POSITIVE_SCENARIOS]
)
def test_vagrant_scenario(
    scenario_name,
    require_command_success,
    vagrant_testbox,
    molecule_scenario,
):
    """Run a checked-in Vagrant scenario."""
    require_command_success(["vagrant", "--version"])

    molecule_scenario(
        "vagrant",
        scenario_name,
        env={"TESTBOX": vagrant_testbox},
    )


@pytest.mark.runtime
@pytest.mark.parametrize(
    ("scenario_name", "expected_message"),
    [
        # Molecule displays only a truncated module summary in captured output.
        ("invalid", "Failed to validate generated"),
        ("invalid_net", "Invalid network_name value my_network."),
    ],
)
def test_vagrant_invalid_scenario(
    scenario_name,
    expected_message,
    require_command_success,
    molecule_scenario,
):
    """Assert that invalid Vagrant scenarios fail with their diagnostic."""
    require_command_success(["vagrant", "--version"])

    run = molecule_scenario(
        "vagrant",
        scenario_name,
        command="create",
        expected_returncodes=(2, 4),
        cleanup_returncodes=(0, 1, 2, 4),
    )
    assert expected_message in run.result.stdout + run.result.stderr


@pytest.mark.runtime
def test_vagrant_multi_node_scenario(
    require_command_success,
    vagrant_testbox,
    molecule_scenario,
):
    """Run multi-node and verify that both machines reach the Vagrantfile."""
    require_command_success(["vagrant", "--version"])

    run = molecule_scenario(
        "vagrant",
        "multi_node",
        env={"TESTBOX": vagrant_testbox},
    )
    vagrantfile = run.ephemeral_directory / "Vagrantfile"
    content = vagrantfile.read_text()
    assert "instance-1" in content
    assert "instance-2" in content
