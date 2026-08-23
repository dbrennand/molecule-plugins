"""Integration tests for the GCE driver."""

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.gce]
GCE_CONFIGURATION = (
    "GCE_PROJECT_ID",
    "GCP_AUTH_KIND",
    "GCP_SERVICE_ACCOUNT_FILE",
)


@pytest.mark.template
def test_cookiecutter_template_renders_and_lints(render_and_lint_template):
    """Render and lint the import-resolved GCE scenario template."""
    assert render_and_lint_template("gce").name == "default"


@pytest.mark.provider
def test_windows_auth_helper_imports() -> None:
    """The controller-side Windows auth helper imports under provider SDKs."""
    pytest.importorskip("Crypto")
    pytest.importorskip("googleapiclient")
    pytest.importorskip("oauth2client")

    helper = (
        Path(__file__).parent / "molecule" / "windows" / "files" / "windows_auth.py"
    )
    spec = importlib.util.spec_from_file_location("windows_auth", helper)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for callable_name in ("GetCompute", "GetKey", "DecryptPassword", "main"):
        assert callable(getattr(module, callable_name)), callable_name


@pytest.mark.provider
@pytest.mark.parametrize("scenario_name", ["linux", "windows"])
def test_gce_scenario(
    scenario_name,
    require_capability,
    require_provider_preflight,
    molecule_scenario,
):
    """Run a checked-in GCE provider scenario."""
    missing = [name for name in GCE_CONFIGURATION if not os.environ.get(name)]
    require_capability(
        not missing,
        f"Missing GCE configuration variables: {missing}",
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
            "google.cloud.gcp_compute_network_info",
            "--args",
            " ".join(
                [
                    f"project={os.environ['GCE_PROJECT_ID']}",
                    f"auth_kind={os.environ['GCP_AUTH_KIND']}",
                    f"service_account_file={os.environ['GCP_SERVICE_ACCOUNT_FILE']}",
                ]
            ),
        ],
        provider="GCE",
    )

    molecule_scenario("gce", scenario_name, redact_output=True)
