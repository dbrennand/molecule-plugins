"""Reusable support for pytest-managed external integrations."""

import os
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from importlib.resources import as_file, files
from pathlib import Path

import pytest
from cookiecutter.main import cookiecutter

from tests.integration.templates import EXPECTED_TEMPLATE_FILES

TEMPLATE_CONTEXT = {
    "dependency_name": "galaxy",
    "driver_name": "default",
    "molecule_directory": "molecule",
    "provisioner_name": "ansible",
    "role_name": "test_role",
    "scenario_name": "default",
    "verifier_name": "ansible",
}


def _format_command(command: Sequence[str], *, redact: bool) -> str:
    """Format a command without exposing protected arguments when requested."""
    if redact:
        return f"{shlex.quote(command[0])} <redacted arguments>"
    return shlex.join(command)


def require_prerequisite(condition: bool, reason: str, *, required: bool) -> None:
    """Skip an unavailable optional integration or fail a required one."""
    if condition:
        return
    if required:
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    expected_returncodes: tuple[int, ...] = (0,),
    timeout: int = 600,
    redact_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command and raise an assertion with consistent diagnostics."""
    command_env = os.environ.copy()
    command_env.update(env or {})
    command = list(args)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=command_env,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        display_command = _format_command(command, redact=redact_output)
        msg = f"Command timed out after {timeout}s: {display_command} (cwd={cwd})"
        raise AssertionError(msg) from (None if redact_output else exc)

    if result.returncode not in expected_returncodes:
        output = "<redacted>" if redact_output else result.stdout + result.stderr
        display_command = _format_command(command, redact=redact_output)
        msg = (
            f"Command returned {result.returncode}, expected {expected_returncodes}: "
            f"{display_command} (cwd={cwd})\n{output}"
        )
        raise AssertionError(msg)
    return result


def materialize_rendered_playbooks(
    rendered_scenario: Path,
    destination_scenario: Path,
    *,
    render_files: Sequence[str],
    converge_overlay: Path | None = None,
) -> None:
    """Copy requested rendered playbooks and optionally append a YAML fragment.

    Destination playbooks are removed before each materialization so an ignored
    file from an earlier render cannot survive when the current template omits
    it. The overlay is deliberately treated as a YAML list fragment rather than
    a second YAML document; Ansible/Jinja text is kept verbatim.
    """
    assert rendered_scenario.is_dir()
    assert destination_scenario.is_dir()

    for filename in render_files:
        destination = destination_scenario / filename
        destination.unlink(missing_ok=True)
        rendered = rendered_scenario / filename
        if rendered.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered, destination)

    if converge_overlay is None:
        return

    converge = destination_scenario / "converge.yml"
    assert converge.is_file(), f"Rendered converge file is missing: {converge}"
    assert converge_overlay.is_file(), (
        f"Converge overlay is missing: {converge_overlay}"
    )
    overlay_text = converge_overlay.read_text()
    first_meaningful_line = next(
        (
            line.strip()
            for line in overlay_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ),
        "",
    )
    assert first_meaningful_line != "---", (
        "Converge overlay must be a YAML list fragment, not a new document"
    )
    assert not first_meaningful_line.startswith("--- "), (
        "Converge overlay must be a YAML list fragment, not a new document"
    )
    converge_text = converge.read_text().rstrip("\r\n")
    converge.write_text(converge_text + "\n" + overlay_text.lstrip("\r\n"))


def render_driver_template(driver_name: str, output_dir: Path) -> Path:
    """Render the import-resolved driver cookiecutter template.

    Returns the rendered default scenario directory. Raises an assertion when
    the import-resolved template is missing, drops an expected file, or leaves
    unresolved template tokens behind, so the same render is reused by both the
    static render-and-lint tests and runtime scenario runs.
    """
    package = f"molecule_plugins.{driver_name}"
    template_resource = files(package).joinpath("cookiecutter")
    context = {**TEMPLATE_CONTEXT, "driver_name": driver_name}

    with as_file(template_resource) as template_path:
        assert Path(template_path, "cookiecutter.json").is_file()
        rendered_root = Path(
            cookiecutter(
                str(template_path),
                no_input=True,
                output_dir=str(output_dir),
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

    return scenario_path
