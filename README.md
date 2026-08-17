# molecule-plugins

This repository contains the following molecule plugins:

- azure
- containers
- docker
- ec2
- gce
- openstack
- podman
- vagrant

Installing `molecule-plugins` does not install dependencies specific to each,
plugin. To install these you need to install the extras for each plugin, like
`pip3 install 'molecule-plugins[azure]'`.

Before installing these plugins be sure that you uninstall their old standalone
packages, like `pip3 uninstall molecule-azure`. If you fail to do so, you will
end-up with a broken setup, as multiple plugins will have the same entry points,
registered.

## Testing

The test suite uses pytest as its behavioral entry point. Driver unit tests live
under `tests/units/`; driver integration projects and their Molecule scenarios
live under `tests/integration/<driver>/`.

Run the deterministic checks from a locked environment:

```bash
uv run --locked --all-extras pytest tests/units
uv run --locked --all-extras pytest tests/integration -m template
uv run --locked --no-default-groups --group lint prek run --all-files
uv run --locked --no-default-groups --group lint ruff format --check tests
```

Runtime and provider integrations check their prerequisites at test time. When a
runtime, executable, or provider configuration is unavailable, a normal local run
skips the affected tests with a reason. Jobs that are expected to exercise an
integration must add `--require-integration`; missing prerequisites then fail
instead of producing a successful all-skipped job. For example:

```bash
uv run --locked --all-extras pytest tests/integration/docker \
  -m runtime --require-integration
```

Docker, Podman, Containers, and Vagrant tests require their corresponding local
runtime. Azure, EC2, GCE, and OpenStack tests require protected provider
configuration and are run by the manual `Provider integration` workflow. Do not
put credentials in test files or command-line arguments.

Select any configured driver through its directory and marker:

```bash
DRIVER=podman
uv run --locked --all-extras pytest "tests/integration/${DRIVER}" \
  -m runtime --require-integration

DRIVER=ec2
uv run --locked --all-extras pytest "tests/integration/${DRIVER}" \
  -m provider --require-integration
```

Provider SDKs live in the locked `provider` dependency group. GCE
integration and its Windows-auth helper additionally require that group:

```bash
uv run --locked --all-extras --group provider \
  pytest tests/integration/gce -m provider --require-integration
```

Azure also needs the azcollection's own SDK pins. The `Provider integration`
workflow installs them from the installed collection's
`requirements-azure.txt` and runs pytest with `--no-sync` so the locked
environment is not resynchronized away.

Positive Molecule lifecycles pass `--destroy always` and register a focused
scenario destroy finalizer. When a lifecycle or cleanup command fails, pytest
reports the isolated Molecule ephemeral directory. After correcting the runtime
or provider problem, cleanup can be retried from the owning driver project:

```bash
cd tests/integration/<driver>
MOLECULE_EPHEMERAL_DIRECTORY=<reported-directory> \
  uv run --locked molecule destroy --scenario-name <scenario>
```

Cleanup output for cloud providers is intentionally redacted. Use the protected
provider console or audit logs when the stable pytest diagnostic is insufficient;
do not add credential values to test output while troubleshooting.

Validate distributions separately:

```bash
uv run --locked --no-default-groups --group pkg python -m build
uv run --locked --no-default-groups --group pkg twine check --strict dist/*
```

## Creating new releases

The `release.yml` workflow generates the wheel and uploads the release to PyPI.
Here are the steps you need to kick that process off:

1. Use a calver tag in the format vYY.MM.DD.

2. Create a new tag and push it to the repo.

   ```bash
   git tag -s <NEW_VERSION> -m "Tag message"
   git push --tags upstream
   ```

   > It is possible to create lightweight tags using `git tag <NEW_VERSION>` but signed tags are preferred.

3. Publish the release with either the GitHub CLI or in a browser.
   See the [GitHub documentation about managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
4. Check the [release workflow](https://github.com/ansible-community/molecule-plugins/actions/workflows/release.yml) runs successfully.
5. Verify the new version is available from the [molecule-plugins](https://pypi.org/project/molecule-plugins/) page on PyPI.
