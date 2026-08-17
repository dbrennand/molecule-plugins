"""Reusable support for pytest-managed external integrations."""

import os
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest


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
        raise AssertionError(msg) from exc

    if result.returncode not in expected_returncodes:
        output = "<redacted>" if redact_output else result.stdout + result.stderr
        display_command = _format_command(command, redact=redact_output)
        msg = (
            f"Command returned {result.returncode}, expected {expected_returncodes}: "
            f"{display_command} (cwd={cwd})\n{output}"
        )
        raise AssertionError(msg)
    return result
