"""Suite-wide pytest configuration."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register integration execution policy options."""
    parser.addoption(
        "--require-integration",
        action="store_true",
        default=False,
        help="Fail rather than skip when a selected integration prerequisite is absent.",
    )


@pytest.fixture(scope="session")
def integration_required(request: pytest.FixtureRequest) -> bool:
    """Return whether selected integrations must have all prerequisites."""
    return bool(request.config.getoption("--require-integration"))
