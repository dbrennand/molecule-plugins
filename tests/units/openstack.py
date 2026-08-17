"""Unit tests for the OpenStack driver."""


def test_openstack_driver_is_detected(registered_drivers):
    """Assert that Molecule recognizes the OpenStack driver."""
    assert "openstack" in registered_drivers
