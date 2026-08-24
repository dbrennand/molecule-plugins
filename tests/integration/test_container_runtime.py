"""Optional end-to-end tests for local container runtimes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.runtime]

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "container"


def runtime_is_ready(executable):
    """Return whether the local container engine can answer an info request."""
    try:
        result = subprocess.run(
            [executable, "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.parametrize("driver_name", ["docker", "podman"])
def test_container_driver_completes_molecule_lifecycle(driver_name, tmp_path):
    executable = shutil.which(driver_name)
    if executable is None:
        pytest.skip(f"{driver_name} executable is not installed")
    if not runtime_is_ready(executable):
        pytest.skip(f"{driver_name} service is not available")

    molecule = shutil.which("molecule")
    assert molecule is not None
    project = tmp_path / "project"
    scenario = project / "molecule" / "default"
    shutil.copytree(FIXTURE_ROOT, scenario)
    molecule_config = scenario / "molecule.yml"
    molecule_config.write_text(
        molecule_config.read_text(encoding="utf-8").replace("__DRIVER__", driver_name),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"ANSIBLE_FORCE_COLOR": "0", "MOLECULE_NO_LOG": "1"})

    result = subprocess.run(
        [molecule, "test", "--scenario-name", "default", "--destroy", "always"],
        check=False,
        capture_output=True,
        cwd=project,
        env=env,
        text=True,
        timeout=900,
    )

    assert result.returncode == 0, (
        f"molecule test failed for {driver_name}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
