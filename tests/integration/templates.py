"""Static expectations for packaged driver templates.

This module is intentionally dependency-free so packaging checks and layout
unit tests can import it without the test or lint dependency groups.
"""

EXPECTED_TEMPLATE_FILES = {
    "azure": {"INSTALL.rst", "converge.yml", "create.yml", "destroy.yml"},
    "containers": {"converge.yml"},
    "docker": {"converge.yml"},
    "ec2": {
        "INSTALL.rst",
        "converge.yml",
        "create.yml",
        "destroy.yml",
        "prepare.yml",
    },
    "gce": {"converge.yml"},
    "openstack": {"converge.yml"},
    "podman": {"converge.yml"},
    "vagrant": {"INSTALL.rst", "converge.yml"},
}
