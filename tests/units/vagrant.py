"""Unit tests for the Vagrant driver."""


def test_vagrant_driver_is_detected(registered_drivers):
    """Assert that Molecule recognizes the Vagrant driver."""
    assert "vagrant" in registered_drivers
