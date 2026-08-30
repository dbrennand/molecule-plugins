"""Optional end-to-end tests for local container runtimes."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.runtime]

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "container"
DOCKER_BUILD_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "docker-build"
RUNTIME_CASES = (
    {
        "id": "docker",
        "driver": "docker",
        "backend_env": {},
        "executable": "docker",
        "fixture_root": FIXTURE_ROOT,
        "scenario": "runtime-docker",
    },
    {
        "id": "podman",
        "driver": "podman",
        "backend_env": {},
        "executable": "podman",
        "fixture_root": FIXTURE_ROOT,
        "scenario": "runtime-podman",
    },
    {
        "id": "docker-build",
        "driver": "docker",
        "backend_env": {},
        "executable": "docker",
        "fixture_root": DOCKER_BUILD_FIXTURE_ROOT,
        "scenario": "runtime-docker-build",
    },
    {
        "id": "containers-docker",
        "driver": "containers",
        "backend_env": {"MOLECULE_CONTAINERS_BACKEND": "docker"},
        "executable": "docker",
        "fixture_root": FIXTURE_ROOT,
        "scenario": "runtime-containers-docker",
    },
)


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


def run_molecule_lifecycle(
    driver_name, fixture_root, scenario_name, tmp_path, extra_env=None
):
    """Run one Molecule lifecycle in isolated project and ephemeral directories."""
    molecule = shutil.which("molecule")
    assert molecule is not None
    project = tmp_path / f"project-{driver_name}"
    ephemeral = tmp_path / f"ephemeral-{driver_name}"
    scenario = project / "molecule" / scenario_name
    shutil.copytree(fixture_root, scenario)
    molecule_config = scenario / "molecule.yml"
    molecule_config.write_text(
        molecule_config.read_text(encoding="utf-8").replace("__DRIVER__", driver_name),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "ANSIBLE_FORCE_COLOR": "0",
            "MOLECULE_NO_LOG": "1",
            "MOLECULE_EPHEMERAL_DIRECTORY": str(ephemeral),
        },
    )
    if extra_env:
        env.update(extra_env)

    try:
        return subprocess.run(
            [molecule, "test", "--scenario-name", scenario_name, "--destroy", "always"],
            check=False,
            capture_output=True,
            cwd=project,
            env=env,
            text=True,
            timeout=900,
        )
    finally:
        subprocess.run(
            [molecule, "destroy", "--scenario-name", scenario_name],
            check=False,
            capture_output=True,
            cwd=project,
            env=env,
            text=True,
            timeout=180,
        )


@pytest.mark.parametrize("case", RUNTIME_CASES[:2], ids=lambda case: case["id"])
def test_container_driver_completes_molecule_lifecycle(case, tmp_path):
    """Verify each direct container driver completes an isolated lifecycle."""
    driver_name = case["driver"]
    executable = shutil.which(case["executable"])
    if executable is None:
        pytest.skip(f"{driver_name} executable is not installed")
    if not runtime_is_ready(executable):
        pytest.skip(f"{driver_name} service is not available")

    result = run_molecule_lifecycle(
        driver_name,
        case["fixture_root"],
        case["scenario"],
        tmp_path,
        extra_env=case["backend_env"],
    )
    assert result.returncode == 0, (
        f"Molecule lifecycle failed for {driver_name}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_docker_custom_build_context_contains_sentinel(tmp_path):
    """Verify Docker builds a custom scenario context into the container."""
    case = RUNTIME_CASES[2]
    executable = shutil.which(case["executable"])
    if executable is None:
        pytest.skip("docker executable is not installed")
    if not runtime_is_ready(executable):
        pytest.skip("docker service is not available")
    scenario_name = case["scenario"]
    result = run_molecule_lifecycle(
        case["driver"],
        case["fixture_root"],
        scenario_name,
        tmp_path,
        extra_env=case["backend_env"],
    )
    assert result.returncode == 0, (
        "custom Docker build-context lifecycle failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_containers_facade_uses_docker_backend(tmp_path):
    """Verify the Containers facade selects Docker before its driver import."""
    case = RUNTIME_CASES[3]
    executable = shutil.which(case["executable"])
    if executable is None:
        pytest.skip("docker executable is not installed")
    if not runtime_is_ready(executable):
        pytest.skip("docker service is not available")

    docker_path = str(Path(executable).parent)
    path = docker_path + os.pathsep + os.environ.get("PATH", "")
    env = os.environ.copy()
    env.update(case["backend_env"])
    env["PATH"] = path
    selection = subprocess.run(
        [
            sys.executable,
            "-c",
            "import molecule_plugins.containers.driver as selected; print(selected.driver)",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert selection.returncode == 0, selection.stderr
    assert selection.stdout.strip() == "docker"

    scenario_name = case["scenario"]
    result = run_molecule_lifecycle(
        case["driver"],
        case["fixture_root"],
        scenario_name,
        tmp_path,
        extra_env={**case["backend_env"], "PATH": path},
    )
    assert result.returncode == 0, (
        "Containers-on-Docker lifecycle failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
