"""Regression coverage for test-time rendered Molecule scenario playbooks."""

from pathlib import Path

import pytest

from tests.integration.support import (
    materialize_rendered_playbooks,
    render_driver_template,
    run_command,
)

pytestmark = [pytest.mark.integration, pytest.mark.template]
MARKER_OVERLAY = Path(__file__).with_name("molecule-marker-tasks.yml")


def _scaffold_project(root: Path) -> Path:
    """Create the minimal project and role layout used by rendered scenarios."""
    scenario = root / "molecule" / "default"
    scenario.mkdir(parents=True)
    role_tasks = root / "roles" / "test_role" / "tasks"
    role_tasks.mkdir(parents=True)
    (role_tasks / "main.yml").write_text(
        "---\n"
        "- name: Test role\n"
        "  ansible.builtin.debug:\n"
        '    msg: "molecule-plugins test role"\n'
    )
    return scenario


def test_materialization_removes_stale_playbooks_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """Requested stale files are removed and repeated rendering is stable."""
    rendered = tmp_path / "rendered"
    destination = tmp_path / "destination"
    rendered.mkdir()
    destination.mkdir()
    (rendered / "converge.yml").write_text("---\n- name: Converge\n  hosts: all\n")
    (destination / "converge.yml").write_text("stale converge\n")
    (destination / "create.yml").write_text("stale create\n")

    materialize_rendered_playbooks(
        rendered,
        destination,
        render_files=("converge.yml", "create.yml"),
    )
    first_snapshot = {
        path.name: path.read_text() for path in destination.iterdir() if path.is_file()
    }

    assert first_snapshot == {"converge.yml": "---\n- name: Converge\n  hosts: all\n"}

    materialize_rendered_playbooks(
        rendered,
        destination,
        render_files=("converge.yml", "create.yml"),
    )

    assert {
        path.name: path.read_text() for path in destination.iterdir() if path.is_file()
    } == first_snapshot


def test_materialization_rejects_second_yaml_document(tmp_path: Path) -> None:
    """Overlays must be list fragments, not a second YAML document."""
    rendered = tmp_path / "rendered"
    destination = tmp_path / "destination"
    rendered.mkdir()
    destination.mkdir()
    (rendered / "converge.yml").write_text("---\n- name: Converge\n  hosts: all\n")
    overlay = tmp_path / "bad-overlay.yml"
    overlay.write_text("\n# comment\n---\n- name: Duplicate document\n")

    with pytest.raises(AssertionError, match="YAML list fragment"):
        materialize_rendered_playbooks(
            rendered,
            destination,
            render_files=("converge.yml",),
            converge_overlay=overlay,
        )


def test_rendered_provider_converge_with_marker_overlay_syntax_checks(
    tmp_path: Path,
    driver_name: str,
) -> None:
    """Azure and EC2 rendered converge files remain one valid YAML document."""
    rendered = render_driver_template(driver_name, tmp_path / f"rendered-{driver_name}")
    project = tmp_path / f"project-{driver_name}"
    scenario = _scaffold_project(project)

    materialize_rendered_playbooks(
        rendered,
        scenario,
        render_files=("converge.yml",),
        converge_overlay=MARKER_OVERLAY,
    )

    result = run_command(
        [
            "ansible-playbook",
            "--syntax-check",
            "--inventory",
            "localhost,",
            "molecule/default/converge.yml",
        ],
        cwd=project,
    )

    assert result.returncode == 0


@pytest.fixture(params=["azure", "ec2"])
def driver_name(request: pytest.FixtureRequest) -> str:
    """Return each provider whose rendered converge is overlay-tested."""
    return request.param
