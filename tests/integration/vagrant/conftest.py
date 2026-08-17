"""Vagrant driver-specific fixtures."""

import os
import warnings
from shutil import copy2, which

import pytest

from tests.integration.conftest import REPOSITORY_ROOT
from tests.integration.support import require_prerequisite
from tests.integration.support import (
    run_command as execute_command,
)


@pytest.fixture(autouse=True)
def _vagrant_module_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose the bundled vagrant Ansible module to scenario playbooks."""
    module_directory = (
        REPOSITORY_ROOT / "src" / "molecule_plugins" / "vagrant" / "modules"
    )
    existing = os.environ.get("ANSIBLE_LIBRARY")
    library_path = (
        f"{existing}{os.pathsep}{module_directory}"
        if existing
        else str(module_directory)
    )
    monkeypatch.setenv("ANSIBLE_LIBRARY", library_path)


@pytest.fixture(scope="session")
def vagrant_testbox(
    tmp_path_factory: pytest.TempPathFactory,
    integration_required: bool,
) -> str:
    """Build and cache the Vagrant test box when one was not supplied."""
    configured_box = os.environ.get("TESTBOX")
    if configured_box:
        return configured_box

    require_prerequisite(
        which("vagrant") is not None,
        "Required executable not found: vagrant",
        required=integration_required,
    )
    box_list = execute_command(["vagrant", "box", "list"], cwd=REPOSITORY_ROOT)
    if any(
        line.split(maxsplit=1)[0] == "testbox"
        for line in box_list.stdout.splitlines()
        if line
    ):
        return "testbox"

    workspace = tmp_path_factory.mktemp("vagrant-testbox")
    copy2(
        REPOSITORY_ROOT / "tests/integration/vagrant/testbox/Vagrantfile",
        workspace / "Vagrantfile",
    )
    box_archive = workspace / "testbox.box"
    build_error: AssertionError | None = None
    try:
        execute_command(
            ["vagrant", "global-status", "--prune"],
            cwd=workspace,
            timeout=120,
        )
        execute_command(["vagrant", "up", "--no-tty"], cwd=workspace, timeout=1200)
        execute_command(["vagrant", "halt"], cwd=workspace, timeout=300)
        execute_command(
            ["vagrant", "package", "--output", str(box_archive)],
            cwd=workspace,
            timeout=600,
        )
        execute_command(
            ["vagrant", "box", "add", str(box_archive), "--name", "testbox"],
            cwd=workspace,
            timeout=600,
        )
    except AssertionError as exc:
        build_error = exc
        require_prerequisite(
            False,
            f"Unable to build the Vagrant testbox: {exc}",
            required=integration_required,
        )
    finally:
        try:
            execute_command(
                ["vagrant", "destroy", "--force"],
                cwd=workspace,
                expected_returncodes=(0, 1),
                timeout=300,
            )
        except AssertionError as exc:
            cleanup_message = f"Vagrant testbox cleanup failed: {exc}"
            if build_error is None:
                raise AssertionError(cleanup_message) from exc
            warnings.warn(cleanup_message)
    return "testbox"
