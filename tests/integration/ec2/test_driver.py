"""Integration tests for the EC2 driver."""

import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ec2]
EC2_CONFIGURATION = ("AWS_IMAGE_ID", "AWS_REGION", "AWS_VPC_SUBNET_ID")


def _aws_credentials_available() -> bool:
    """Return whether an AWS profile or explicit access keys are configured."""
    return bool(os.environ.get("AWS_PROFILE")) or bool(
        os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
    )


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the packaged EC2 scenario template."""
    assert render_and_lint_template("ec2").name == "default"


@pytest.mark.provider
@pytest.mark.parametrize("scenario_name", ["default", "multi_node"])
def test_ec2_scenario(
    scenario_name,
    require_capability,
    require_provider_preflight,
    molecule_scenario,
):
    """Run a checked-in EC2 provider scenario."""
    missing = [name for name in EC2_CONFIGURATION if not os.environ.get(name)]
    require_capability(
        _aws_credentials_available() and not missing,
        "AWS credentials and protected EC2 configuration are required; "
        f"missing configuration: {missing}",
    )
    require_provider_preflight(
        [
            "ansible",
            "localhost",
            "--inventory",
            "localhost,",
            "--connection",
            "local",
            "--module-name",
            "amazon.aws.aws_caller_info",
            "--args",
            f"region={os.environ['AWS_REGION']}",
        ],
        provider="EC2",
    )

    molecule_scenario("ec2", scenario_name, redact_output=True)
