"""Unit tests for the GCE driver."""


def test_gce_driver_is_detected(registered_drivers):
    """Assert that Molecule recognizes the GCE driver."""
    assert "gce" in registered_drivers
