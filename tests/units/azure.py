"""Unit tests for the Azure driver."""


def test_azure_driver_is_detected(registered_drivers):
    """Assert that Molecule recognizes the Azure driver."""
    assert "azure" in registered_drivers
