"""Unit tests for the pytest integration harness."""

import sys
from pathlib import Path

import pytest

from tests.integration.support import require_prerequisite, run_command


def test_missing_optional_prerequisite_skips() -> None:
    """Missing optional integrations skip in local runs."""
    with pytest.raises(pytest.skip.Exception, match="runtime unavailable"):
        require_prerequisite(False, "runtime unavailable", required=False)


def test_missing_required_prerequisite_fails() -> None:
    """Missing selected CI integrations fail instead of silently skipping."""
    with pytest.raises(pytest.fail.Exception, match="runtime unavailable"):
        require_prerequisite(False, "runtime unavailable", required=True)


def test_command_failure_contains_actionable_diagnostics(tmp_path: Path) -> None:
    """Command errors include both output streams and execution metadata."""
    command = [
        sys.executable,
        "-c",
        "import sys; print('from stdout'); print('from stderr', file=sys.stderr); sys.exit(3)",
    ]

    with pytest.raises(AssertionError) as error:
        run_command(command, cwd=tmp_path)

    message = str(error.value)
    assert "returned 3" in message
    assert str(tmp_path) in message
    assert "from stdout" in message
    assert "from stderr" in message


def test_redacted_command_failure_omits_arguments_and_output(tmp_path: Path) -> None:
    """Protected provider diagnostics do not expose arguments or process output."""
    protected_value = "sensitive-provider-value"
    command = [
        sys.executable,
        "-c",
        f"import sys; print('{protected_value}'); sys.exit(3)",
    ]

    with pytest.raises(AssertionError) as error:
        run_command(command, cwd=tmp_path, redact_output=True)

    message = str(error.value)
    assert protected_value not in message
    assert command[2] not in message
    assert "<redacted arguments>" in message
    assert "<redacted>" in message


def test_redacted_timeout_omits_arguments_from_chained_exception(
    tmp_path: Path,
) -> None:
    """Timed-out protected commands never surface arguments in diagnostics."""
    protected_value = "sensitive-timeout-value"
    command = [
        sys.executable,
        "-c",
        f"import time; print('{protected_value}'); time.sleep(30)",
    ]

    with pytest.raises(AssertionError) as error:
        run_command(command, cwd=tmp_path, timeout=1, redact_output=True)

    message = str(error.value)
    assert protected_value not in message
    assert command[2] not in message
    assert "<redacted arguments>" in message
    assert error.value.__cause__ is None
