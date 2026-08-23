"""Deterministic layout assertions for the pytest-owned test tree."""

from pathlib import Path

import pytest

from tests.integration.templates import EXPECTED_TEMPLATE_FILES

TESTS_ROOT = Path(__file__).parents[1]
INTEGRATION_ROOT = TESTS_ROOT / "integration"

EXPECTED_SCENARIOS = {
    "azure": ["default", "multi_node"],
    "containers": ["default"],
    "docker": ["default", "env_substitution", "with_context"],
    "ec2": ["default", "multi_node"],
    "gce": ["linux", "windows"],
    "openstack": ["default", "multiple", "network", "security_group", "volume"],
    "podman": ["default"],
    "vagrant": [
        "box_url",
        "config_options",
        "default",
        "default_compat",
        "hostname",
        "invalid",
        "invalid_net",
        "multi_node",
        "network",
        "provider_config_options",
        "vagrant_root",
    ],
}


@pytest.mark.parametrize("driver_name", sorted(EXPECTED_SCENARIOS))
def test_driver_scenario_layout(driver_name: str) -> None:
    """Each driver owns exactly its mapped scenarios with a molecule.yml."""
    scenarios = sorted(EXPECTED_SCENARIOS[driver_name])
    project = INTEGRATION_ROOT / driver_name
    assert project.is_dir()
    molecule = project / "molecule"
    discovered = sorted(entry.name for entry in molecule.iterdir() if entry.is_dir())
    assert discovered == scenarios
    for scenario in scenarios:
        assert (molecule / scenario / "molecule.yml").is_file()


def test_scenario_map_matches_template_map() -> None:
    """The scenario and template expectations cover the same driver set."""
    assert sorted(EXPECTED_SCENARIOS) == sorted(EXPECTED_TEMPLATE_FILES)
    total_scenarios = sum(len(scenarios) for scenarios in EXPECTED_SCENARIOS.values())
    assert total_scenarios == 27
    for driver_name, expected_files in EXPECTED_TEMPLATE_FILES.items():
        assert expected_files, driver_name
