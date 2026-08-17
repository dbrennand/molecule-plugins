"""Shared fixtures for driver integration tests."""

import subprocess
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from shutil import which

import pytest
from cookiecutter.main import cookiecutter

from tests.integration.support import (
    require_prerequisite,
)
from tests.integration.support import (
    run_command as execute_command,
)
from tests.integration.templates import EXPECTED_TEMPLATE_FILES

REPOSITORY_ROOT = Path(__file__).parents[2]
TEMPLATE_CONTEXT = {
    "dependency_name": "galaxy",
    "driver_name": "default",
    "molecule_directory": "molecule",
    "provisioner_name": "ansible",
    "role_name": "test_role",
    "scenario_name": "default",
    "verifier_name": "ansible",
}

MOLECULE_CALL_FAILED = pytest.StashKey[bool]()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Record the call-phase outcome so cleanup cannot mask a failure."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.stash[MOLECULE_CALL_FAILED] = report.failed


@dataclass(frozen=True)
class MoleculeRun:
    """Result and isolated state directory for one Molecule invocation."""

    result: subprocess.CompletedProcess[str]
    ephemeral_directory: Path


@pytest.fixture
def run_command() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Expose the tested subprocess helper as a fixture."""
    return execute_command


@pytest.fixture
def require_capability(
    integration_required: bool,
) -> Callable[[bool, str], None]:
    """Return a local-skip or selected-CI-fail prerequisite gate."""

    def require(condition: bool, reason: str) -> None:
        require_prerequisite(condition, reason, required=integration_required)

    return require


@pytest.fixture
def require_executable(
    require_capability: Callable[[bool, str], None],
) -> Callable[[str], str]:
    """Return a gate for required external executables."""

    def require(name: str) -> str:
        executable = which(name)
        require_capability(
            executable is not None, f"Required executable not found: {name}"
        )
        assert executable is not None
        return executable

    return require


@pytest.fixture
def require_command_success(
    require_executable: Callable[[str], str],
    require_capability: Callable[[bool, str], None],
) -> Callable[[Sequence[str]], None]:
    """Return a bounded active capability probe."""

    def require(args: Sequence[str]) -> None:
        require_executable(args[0])
        try:
            result = subprocess.run(
                list(args),
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            require_capability(False, f"Capability probe timed out: {' '.join(args)}")
            return
        output = (result.stdout + result.stderr).strip()
        require_capability(
            result.returncode == 0,
            f"Capability probe failed: {' '.join(args)}\n{output}",
        )

    return require


@pytest.fixture
def require_provider_preflight(
    require_executable: Callable[[str], str],
    require_capability: Callable[[bool, str], None],
) -> Callable[..., None]:
    """Return a sanitized read-only provider authentication/context gate."""

    def require(args: Sequence[str], *, provider: str) -> None:
        require_executable(args[0])
        try:
            execute_command(
                args,
                cwd=REPOSITORY_ROOT,
                timeout=120,
                redact_output=True,
            )
        except AssertionError:
            require_capability(
                False,
                f"{provider} read-only authentication/context preflight failed",
            )

    return require


@pytest.fixture
def require_container_runtime(
    require_capability: Callable[[bool, str], None],
) -> Callable[[], str]:
    """Return a gate that accepts either a reachable Docker or Podman runtime."""

    def require() -> str:
        diagnostics: list[str] = []
        for name in ("docker", "podman"):
            if which(name) is None:
                diagnostics.append(f"{name}: executable missing")
                continue
            try:
                result = subprocess.run(
                    [name, "info"],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=20,
                )
            except subprocess.TimeoutExpired:
                diagnostics.append(f"{name}: info timed out")
                continue
            if result.returncode == 0:
                return name
            diagnostics.append(f"{name}: info returned {result.returncode}")

        require_capability(
            False,
            "No reachable container runtime (" + "; ".join(diagnostics) + ")",
        )
        message = "unreachable after prerequisite gate"
        raise AssertionError(message)

    return require


@pytest.fixture
def molecule_scenario(
    tmp_path: Path,
    request: pytest.FixtureRequest,
    run_command: Callable[..., subprocess.CompletedProcess[str]],
    require_executable: Callable[[str], str],
) -> Callable[..., MoleculeRun]:
    """Return a helper that invokes one checked-in Molecule scenario."""

    def run(
        driver_name: str,
        scenario_name: str,
        *,
        command: str = "test",
        env: dict[str, str] | None = None,
        expected_returncodes: tuple[int, ...] = (0,),
        cleanup_returncodes: tuple[int, ...] = (0,),
        timeout: int = 3600,
        redact_output: bool = False,
    ) -> MoleculeRun:
        require_executable("molecule")
        project_directory = REPOSITORY_ROOT / "tests/integration" / driver_name
        scenario_directory = project_directory / "molecule" / scenario_name
        assert (scenario_directory / "molecule.yml").is_file()

        ephemeral_directory = tmp_path / f"{driver_name}-{scenario_name}"
        command_env = {
            "ANSIBLE_FORCE_COLOR": "0",
            "MOLECULE_EPHEMERAL_DIRECTORY": str(ephemeral_directory),
            **(env or {}),
        }

        def cleanup() -> None:
            try:
                execute_command(
                    ["molecule", "destroy", "--scenario-name", scenario_name],
                    cwd=project_directory,
                    env=command_env,
                    timeout=900,
                    expected_returncodes=cleanup_returncodes,
                    redact_output=redact_output,
                )
            except AssertionError as exc:
                message = f"{exc}\nMolecule ephemeral directory: {ephemeral_directory}"
                if request.node.stash.get(MOLECULE_CALL_FAILED, False):
                    warnings.warn(message)
                    return
                raise AssertionError(message) from exc

        request.addfinalizer(cleanup)
        command_args = ["molecule", command, "--scenario-name", scenario_name]
        if command == "test":
            command_args.extend(["--destroy", "always"])
        try:
            result = run_command(
                command_args,
                cwd=project_directory,
                env=command_env,
                expected_returncodes=expected_returncodes,
                timeout=timeout,
                redact_output=redact_output,
            )
        except AssertionError as exc:
            message = f"{exc}\nMolecule ephemeral directory: {ephemeral_directory}"
            raise AssertionError(message) from exc
        return MoleculeRun(result=result, ephemeral_directory=ephemeral_directory)

    return run


@pytest.fixture
def render_and_lint_template(
    tmp_path: Path,
    run_command: Callable[..., subprocess.CompletedProcess[str]],
) -> Callable[[str], Path]:
    """Return a helper that renders and lints one packaged driver template."""

    def render(driver_name: str) -> Path:
        package = f"molecule_plugins.{driver_name}"
        template_resource = files(package).joinpath("cookiecutter")
        context = {**TEMPLATE_CONTEXT, "driver_name": driver_name}

        with as_file(template_resource) as template_path:
            assert Path(template_path, "cookiecutter.json").is_file()
            rendered_root = Path(
                cookiecutter(
                    str(template_path),
                    no_input=True,
                    output_dir=tmp_path,
                    extra_context=context,
                )
            )

        scenario_path = rendered_root / "default"
        assert scenario_path.is_dir()
        for expected_file in EXPECTED_TEMPLATE_FILES[driver_name]:
            assert (scenario_path / expected_file).is_file()

        for rendered_file in scenario_path.rglob("*"):
            if not rendered_file.is_file():
                continue
            content = rendered_file.read_text()
            assert "cookiecutter." not in content
            assert "{% raw %}" not in content
            assert "{% endraw %}" not in content

        run_command(
            [
                "ansible-lint",
                "--offline",
                "--config-file",
                str(REPOSITORY_ROOT / "tests/integration/ansible-lint.yml"),
                "--project-dir",
                str(tmp_path),
                str(scenario_path),
            ],
            cwd=REPOSITORY_ROOT,
        )
        return scenario_path

    return render
