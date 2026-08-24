# Clean-room pytest suite implementation plan

> **For Hermes:** Implement this plan task-by-task without consulting or copying the repository's current tests.

**Goal:** Replace the project's test suite with a small, independent pytest suite that checks the public behavior of every Molecule driver and provides useful integration coverage without requiring paid cloud infrastructure.

**Architecture:** Use one conventional `tests/` tree split into `unit/` and `integration/`. Unit tests call Python APIs with small `SimpleNamespace` configurations and monkeypatch only external boundaries. Integration tests load the installed Molecule entry points, validate packaged templates/playbooks/schemas, and optionally exercise Docker or Podman through a real `molecule test` run.

**Tech stack:** pytest, Python standard library, Molecule/Ansible/Jinja2/jsonschema already supplied by the project environment. Do not add a mocking framework, coverage gate, snapshot tool, fixture plugin, or cloud SDK solely for tests.

---

## Clean-room constraints and KISS rules

- The existing tests were not inspected while preparing this plan. Do not copy, port, or use their expectations during implementation.
- Build expectations only from `src/molecule_plugins/**` and the package entry points in `pyproject.toml:69-77`.
- Keep the default suite offline and deterministic. Azure, EC2, GCE, OpenStack, and Vagrant live infrastructure is out of scope.
- Prefer a single parametrized test over one nearly identical file per driver.
- Assert observable results, commands, warnings, and errors; do not assert private call order or logger text unless the text is the user-facing error contract.
- Use `monkeypatch` and `tmp_path`; do not create a general fake framework.
- Do not require 100% coverage or add a coverage threshold. Missing low-value branches are preferable to brittle tests.
- Keep optional container runtime tests under one `runtime` marker and skip them when the requested executable/daemon is unavailable.

## Source-derived behavior inventory

The new suite must cover these distinct behaviors rather than every line:

- Common SSH-style drivers: Azure (`src/molecule_plugins/azure/driver.py:76-146`), GCE (`src/molecule_plugins/gce/driver.py:80-173`), OpenStack (`src/molecule_plugins/openstack/driver.py:109-196`), Vagrant (`src/molecule_plugins/vagrant/driver.py:127-218`), and the Linux path of EC2 (`src/molecule_plugins/ec2/driver.py:156-283`).
- EC2-specific host selection, platform connection overrides, WinRM password lookup boundary, and missing dependency failures (`src/molecule_plugins/ec2/driver.py:168-274`).
- GCE Linux versus Windows connection dictionaries (`src/molecule_plugins/gce/driver.py:117-152`).
- Docker connection environment, sanity check, reset, collections, and schema (`src/molecule_plugins/docker/driver.py:197-289`).
- Podman executable lookup, compatibility warning/error, reset command, collections, and schema (`src/molecule_plugins/podman/driver.py:162-273`).
- Containers backend selection and backend-specific path/schema handling (`src/molecule_plugins/containers/driver.py:14-71`).
- OpenStack and Vagrant prerequisite checks (`src/molecule_plugins/openstack/driver.py:172-185`, `src/molecule_plugins/vagrant/driver.py:207-209`).
- Docker network filter behavior (`src/molecule_plugins/docker/playbooks/filter_plugins/get_docker_networks.py:4-37`).
- Vagrant's standalone recursive dictionary merge and the smallest useful configuration validation (`src/molecule_plugins/vagrant/modules/vagrant.py:349-367`, `src/molecule_plugins/vagrant/modules/vagrant.py:611-689`).
- Package resources: eight cookiecutter roots, 34 YAML playbook/template files, three JSON driver schemas, and eight `molecule.driver` entry points.

The GCE `windows_auth.py` script imports undeclared `googleapiclient` and PyCrypto modules at import time. Do not add those packages or fake their module trees merely to unit-test this embedded script. Cover it initially as a packaged Python resource that compiles; add behavioral tests only if its dependencies become an explicit supported extra.

---

### Task 1: Establish the minimal pytest layout

**Objective:** Make only the clean-room suite collect by default and document the two useful test classes.

**Files:**

- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Modify: `pyproject.toml:8-13`
- Modify: `pyproject.toml:123-127`

**Steps:**

1. Start with an empty `tests/` directory; do not open or copy existing test files. If an old test root must be retained temporarily, keep it outside pytest's `testpaths` until the new suite passes.
2. Remove `pytest-helpers-namespace` from the development group unless another non-test tool demonstrably imports it.
3. Set `testpaths = ["tests"]` and reduce default `addopts` to `-ra`. Retain the explicit `-p no:pytest_ansible` only if collection proves that the transitive plugin is auto-loaded and interferes with plain pytest.
4. Register two markers:
   - `integration`: local integration with the installed package, Molecule, Ansible, or packaged resources.
   - `runtime`: tests requiring Docker or Podman and image/network access.
5. In `tests/conftest.py`, add only one reusable fixture: a `make_config(tmp_path)` factory returning a `SimpleNamespace` with the minimal `scenario`, `driver`, `platforms`, `command_args`, `provisioner`, and `config_data` attributes required by the source drivers. Allow small keyword overrides; do not reproduce Molecule's full `Config` object.
6. Run `uv run pytest --collect-only`. Expected result at this stage: successful collection with no tests, no legacy test files collected, and no unknown-marker warnings.

### Task 2: Test the shared driver contract once

**Objective:** Cover common public behavior with a compact parametrized matrix.

**Files:**

- Create: `tests/unit/test_driver_contracts.py`

**Steps:**

1. Parametrize Azure, EC2, GCE, OpenStack, and Vagrant with class, expected name, and expected cookiecutter directory.
2. For each driver, instantiate it with `make_config()` and assert:
   - `name` is the entry-point name;
   - `template_dir()` is an existing directory containing `cookiecutter.json`;
   - the SSH login template includes address, user, port, identity file, and configured SSH options;
   - `default_safe_files` contains the instance configuration path.
3. Monkeypatch `molecule.util.safe_load_file` with one Linux instance record and assert `login_options()` plus `ansible_connection_options()` expose the source record through the expected Molecule/Ansible keys.
4. Parametrize `StopIteration` and `OSError` from the instance-config boundary and assert `ansible_connection_options()` returns `{}`.
5. Add only the two genuinely distinct branches:
   - GCE Windows returns WinRM fields and `ansible_become_method="runas"`.
   - EC2 platform `connection_options` override defaults; when WinRM has no password, monkeypatch `_get_windows_instance_pass` and assert its returned password is used.
6. Test EC2 login host selection for explicit `--host`, a single platform, and the ambiguous multi-platform `SystemExit(1)` case.
7. Run `uv run pytest tests/unit/test_driver_contracts.py -q`. Expected: all cases pass without cloud credentials or network access.

### Task 3: Test Docker, Podman, Containers, and prerequisite boundaries

**Objective:** Cover local backend decisions and side effects while keeping engines and daemons mocked in unit tests.

**Files:**

- Create: `tests/unit/test_container_drivers.py`

**Steps:**

1. Docker:
   - assert its login command and `login_options()`;
   - assert the default Ansible connection and the additional `-H=<value>` when `DOCKER_HOST` is set;
   - inject a tiny fake `docker` module through `sys.modules` to test successful `ping()` and daemon failure passed to `sysexit_with_message`;
   - use one fake client to assert `reset()` stops/prunes labelled containers and removes labelled networks;
   - assert `required_collections` and that `schema_file()` resolves to an existing JSON file.
2. Podman:
   - monkeypatch module-level `which` to test configured executable resolution and missing-command failure;
   - assert login and Ansible connection options use `MOLECULE_PODMAN_EXECUTABLE`;
   - replace `Runtime` with small old/new-version fakes to test success, the old-Ansible warning, and the old-Ansible-plus-pipelining setup error;
   - monkeypatch `get_app` and assert `reset()` emits exactly the source command for labelled Molecule containers; assert a missing executable skips the command;
   - assert collections and schema path.
3. Containers:
   - test `Container` identity, union of required collections, backend playbook path, and containers-specific schema path using the backend selected in the test process;
   - use two short subprocess tests with controlled `MOLECULE_CONTAINERS_BACKEND` and `PATH` to prove Docker and Podman selection independently. A third subprocess asserts an unsupported backend fails with `NotImplementedError`. Subprocesses avoid fragile module reload and global import cleanup.
4. OpenStack and Vagrant:
   - monkeypatch `_is_module_installed`/`which` and assert missing prerequisites call Molecule's exit helper;
   - include one success case for each and no more.
5. Reset class-level or instance sanity flags inside each test so cases remain order-independent.
6. Run `uv run pytest tests/unit/test_container_drivers.py -q`. Expected: all tests pass whether or not Docker, Podman, Vagrant, or OpenStack services are installed.

### Task 4: Test the two small reusable helpers

**Objective:** Protect meaningful pure transformations without turning embedded scripts into separate projects.

**Files:**

- Create: `tests/unit/test_helpers.py`

**Steps:**

1. For `get_docker_networks`, test one combined input containing:
   - an explicit `docker_networks` entry;
   - a duplicate platform `networks` name;
   - a new platform network;
   - supplied labels.
   Assert deduplication, label merging, and output order in one test. Add one empty-input test.
2. Assert `FilterModule().filters()` exposes the helper under `molecule_get_docker_networks`.
3. For Vagrant `merge_dicts`, assert nested dictionaries merge, scalar/list values from the second mapping replace the first, and neither input is mutated.
4. Add one focused Vagrant configuration test around `_get_instance_vagrant_config_dict`: defaults plus a valid interface. Add two parametrized validation cases for a missing/invalid `network_name` and one checksum-pair validation case. Construct the client with `object.__new__` and only the three attributes that method reads; do not run `VagrantClient.__init__` or launch Vagrant.
5. Compile `src/molecule_plugins/gce/playbooks/files/windows_auth.py` with `py_compile` in an integration resource test rather than importing it here.
6. Run `uv run pytest tests/unit/test_helpers.py -q`. Expected: all tests pass with no processes or network calls.

### Task 5: Verify installed plugins and packaged resources

**Objective:** Test that source files work together with packaging, Molecule, Jinja, Ansible, and jsonschema.

**Files:**

- Create: `tests/integration/test_plugins_and_resources.py`

**Steps:**

1. Mark the module `pytest.mark.integration`.
2. Use `importlib.metadata.entry_points(group="molecule.driver")` and assert the project contributes exactly these names: `azure`, `containers`, `docker`, `ec2`, `gce`, `openstack`, `podman`, and `vagrant`. Load each entry point and assert it is a `molecule.api.Driver` subclass.
3. Run the installed `molecule drivers` executable via `subprocess.run(..., check=True, text=True, capture_output=True)` and assert all eight names appear. Do not assert ordering or exclude Molecule's built-in `default` driver.
4. Parametrize the eight `cookiecutter` directories. Render each into `tmp_path` with Jinja2 using one explicit `cookiecutter` context (`molecule_directory`, `scenario_name`, `role_name`, plus GCE's four extra names). Assert:
   - rendering leaves no `cookiecutter.` tokens;
   - each rendered YAML document loads through Ansible's YAML loader;
   - expected scenario files exist.
5. Parametrize the three `schema/driver.json` files. Parse with `json`, call `jsonschema`'s schema check, and validate one minimal matching driver document (`docker`, `podman`, or `containers`). Add one invalid-name assertion per schema through the same parametrization.
6. Parametrize all packaged `.yml` files under `src/molecule_plugins/*/playbooks` and load them through Ansible's YAML loader. This is a parse/resource test, not an assertion for every task.
7. Use `py_compile.compile(..., doraise=True)` for the two non-driver Python resources: Docker's filter plugin and GCE's Windows helper.
8. Run `uv run pytest tests/integration/test_plugins_and_resources.py -q`. Expected: every entry point loads and every packaged resource validates without contacting a daemon or cloud.

### Task 6: Add one real local-runtime integration path

**Objective:** Prove the two local container drivers can complete Molecule's lifecycle, while keeping this optional and small.

**Files:**

- Create: `tests/integration/test_container_runtime.py`
- Create: `tests/integration/fixtures/container/molecule.yml`
- Create: `tests/integration/fixtures/container/converge.yml`
- Create: `tests/integration/fixtures/container/verify.yml`

**Steps:**

1. Mark the module `integration` and `runtime`.
2. Parametrize only `docker` and `podman`.
3. Before each case, skip if the executable is absent. For Docker, also perform a cheap daemon ping and skip on connection failure.
4. Copy the single minimal fixture scenario to `tmp_path` and substitute only the driver name. Use one readily available Python-capable image, one container, a no-op/debug converge play, and a verify play that asserts the target is reachable. Do not add roles, Testinfra, multiple distributions, systemd, custom networks, or privileged containers.
5. Run `molecule test` in that temporary scenario with a timeout and `MOLECULE_NO_LOG=1`; always request Molecule's normal destroy cleanup.
6. Assert exit code zero. On failure, include captured stdout/stderr in the pytest assertion.
7. Run locally when available: `uv run pytest -m runtime tests/integration/test_container_runtime.py -q`.
8. In CI, enable at most one runtime already provided by the runner. Do not install or configure a second engine merely to expand the matrix.

### Task 7: Remove legacy collection paths and verify the complete suite

**Objective:** Make the clean-room suite the only maintained suite and confirm its fast/offline default.

**Files:**

- Modify: `pyproject.toml:230-276` only where old test paths or helper setup are referenced
- Remove: previous test directories after the new suite passes (delete wholesale; do not migrate individual files)

**Steps:**

1. Run the new offline suite before deleting anything:
   - `uv run pytest -m "not runtime" -q`
   - expected: unit and local integration tests pass; no cloud credentials, daemon, or network required.
2. Remove obsolete pytest/test-path configuration and old test directories so there is one canonical suite under `tests/`.
3. Keep tox's test environment simple: package install followed by `pytest -m "not runtime"`. Remove references to absent inventory files or Galaxy requirements only if the clean suite no longer needs them. Do not redesign unrelated lint/package tox environments.
4. Run the final gates:
   - `uv run pytest --collect-only -q` — only `tests/` is collected;
   - `uv run pytest tests/unit -q` — unit suite passes;
   - `uv run pytest tests/integration -m "integration and not runtime" -q` — offline integration passes;
   - `uv run pytest -m "not runtime" -q` — default suite passes;
   - `uv run ruff check tests` — new tests pass lint;
   - `uv run tox -e py` — packaged test environment passes.
5. If a local engine is available, run the runtime command from Task 6 once and report pass/skip honestly. A skipped runtime test must not be presented as end-to-end verification.

---

## Expected final file tree

```text
tests/
├── conftest.py
├── unit/
│   ├── __init__.py
│   ├── test_driver_contracts.py
│   ├── test_container_drivers.py
│   └── test_helpers.py
└── integration/
    ├── __init__.py
    ├── test_plugins_and_resources.py
    ├── test_container_runtime.py
    └── fixtures/container/
        ├── molecule.yml
        ├── converge.yml
        └── verify.yml
```

## Deliberate exclusions

- No Azure, AWS, GCP, OpenStack, or Vagrant live provisioning.
- No test-per-property for trivial getters/setters or no-op `sanity_checks` methods.
- No tests of generated `_version.py` internals.
- No mocks of entire Molecule, Ansible, cloud SDKs, or container engines.
- No golden files, snapshots, dynamic fixture plugin, custom pytest hooks, coverage threshold, or combinatorial image/platform matrix.
- No behavioral import test for GCE `windows_auth.py` until its direct imports are declared project dependencies.

## Risks and mitigations

- **Import-time backend choice in `containers/driver.py`:** isolate backend-selection assertions in subprocesses instead of reloading modules in-process.
- **Class-level Docker sanity state:** reset `_passed_sanity` explicitly to prevent order dependence.
- **Optional SDK imports:** patch only the boundary used by the driver; never install cloud packages merely to satisfy a unit test.
- **Template syntax has two Jinja layers:** render only `cookiecutter.*`; preserve Ansible expressions for the Ansible loader.
- **Runtime test can be slow or network-sensitive:** exclude it from the default marker expression and keep exactly one image/case per available engine.
- **Current tox configuration references files that are not present in this checkout:** make the clean suite self-contained and remove stale setup only after proving it is unnecessary.

## Completion criteria

- Plain pytest is the only test framework.
- The default suite has both unit and integration tests and runs offline.
- All eight package entry points load through Molecule.
- Shared driver behavior is parametrized rather than duplicated.
- Docker/Podman side effects are unit-tested at their process/SDK boundaries.
- Templates, schemas, playbooks, and embedded Python resources are validated as packaged artifacts.
- At least one actual container-runtime Molecule lifecycle can be run when a supported local engine exists.
- The final suite contains no copied or migrated legacy test implementation.
