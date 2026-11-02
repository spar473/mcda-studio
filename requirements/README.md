# Python 3.12 dependency environments

Package B deliberately targets the current macOS arm64 / Python 3.12 environment and one Linux
x86_64 / Python 3.12 CI job. Other Python/platform combinations are not covered by these locks.
The package's public minimum Python remains 3.12; this is not a tested-platform matrix.

- `runtime-py312.txt`: hash-pinned transitive dependencies for the `api` extra.
- `dev-py312.txt`: hash-pinned application/test/lint/type dependencies for `dev` (including SciPy).
- `build-py312.txt`: hash-pinned build frontend/backend, editable-install helper, pip-tools and pipx, including pip/setuptools.
- `baseline-py312.txt`: constraints retaining the existing verified application's versions during
  packaging work. This is provenance/input to the resolver, **not** a complete install lock.
- `build.in`: intentional build-tool versions. Hatchling also matches `build-system.requires`.

Use an environment with Python 3.12 and install the build lock, then the dev lock if needed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/build-py312.txt -r requirements/dev-py312.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e '.[dev]'
.venv/bin/python -m pip check
```

Generate with the locked pip-tools 7.6.2 (from the repository root):

```sh
.venv/bin/pip-compile --generate-hashes --strip-extras --no-emit-index-url --constraint requirements/baseline-py312.txt --extra api --output-file requirements/runtime-py312.txt pyproject.toml
.venv/bin/pip-compile --generate-hashes --strip-extras --no-emit-index-url --constraint requirements/baseline-py312.txt --extra dev --output-file requirements/dev-py312.txt pyproject.toml
.venv/bin/pip-compile --allow-unsafe --generate-hashes --strip-extras --no-emit-index-url --output-file requirements/build-py312.txt requirements/build.in
```

Review changes in both constraints and lock output when upgrading a baseline version. Do not just
refresh the entire numeric stack for packaging. These pip-compile exports were generated on Mac;
their Linux applicability is checked by the configured CI install/gate, not inferred from a filename.
Hashes cover published distribution artifacts, including platform wheels. No index credentials or
machine-specific package URLs belong in these files.

To make smoke installs offline, download the locked wheels on the target platform first:

```sh
.venv/bin/python -m pip download --require-hashes --only-binary=:all: -r requirements/runtime-py312.txt -r requirements/build-py312.txt --dest /tmp/mcda-wheels
```

A Mac wheelhouse is not a Linux wheelhouse. Consumer pipx resolution uses those verified wheel
files; the direct/rebuilt-wheel venv checks preinstall the runtime lock then install the local
wheel with `--no-deps`. The plain-wheel check starts with a fresh environment and resolves only
base dependencies. No part of this requires PyPI publication of MCDA Studio.
