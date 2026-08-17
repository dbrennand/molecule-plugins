"""Unit tests for the EC2 driver."""


def test_ec2_driver_is_detected(registered_drivers):
    """Assert that Molecule recognizes the EC2 driver."""
    assert "ec2" in registered_drivers
