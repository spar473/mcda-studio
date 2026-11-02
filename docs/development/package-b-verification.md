# Package B: installation and startup verification

Date: 2026-10-26, Pacific/Auckland. Implemented locally on `main`, starting at
`3c382ab5e310d8c2f1b56444772e7d523c34ee36`; no commit, push, tag or publication. Existing local
planning documents and their recorded decisions were preserved. No applicable `AGENTS.md` found.

## Concrete finish line

The direct wheel, the wheel rebuilt from an extracted sdist, and an isolated pipx consumer install
are checked **outside the repository**, with `PYTHONPATH`/resource overrides removed and disposable
libraries. The app serves index/JS/CSS; Chromium opens the bundled VC example, visits Results,
downloads analysis JSON and reloads the saved project. The API also lists/imports all three
examples. Full-precision VC values match the existing reference numbers within 1e-12. The exported
project reproduces exactly through the installed CLI; a new server process reopens the actual
library and returns the same completed record. No numerical expectation was changed.

Artifacts (ignored local `dist/`, not published):

- `dist/direct/mcda_studio-0.1.0-py3-none-any.whl`
- `dist/from-sdist/mcda_studio-0.1.0-py3-none-any.whl`
- `dist/mcda_studio-0.1.0.tar.gz`
- `dist/MANIFEST.sha256`
- `dist/smoke-evidence/result.json`, downloaded browser analysis/project JSON and GUI screenshots.

Both wheel routes have SHA-256
`b035a414465f56052af2caa4bacf781beb2fe4f3aae48fc4f081c7ccb485334e`.
The final sdist hash is recorded in `MANIFEST.sha256`. The smoke record includes hashes, environment
and tested routes. Builds correctly report the source revision **and dirty working tree**; these
are local development artifacts, not a tagged release. The version remains 0.1.0; no version or
project-schema change was needed for packaging.

## Implementation boundary

- Keep base engine/CLI dependencies separate from the existing `api` extra. The GUI installation
  command is `pipx install '/absolute/path/to/mcda_studio-0.1.0-py3-none-any.whl[api]'`.
- Bundle prebuilt GUI assets and only each example's JSON/README as package resources. Ship the
  frontend source and prebuilt assets in the sdist, so rebuilding its wheel needs no Node/network
  asset generation. Missing required GUI assets fail release builds. Editable installs can be
  prepared before frontend assets exist.
- Lookup precedence: explicit argument, existing environment setting, real source checkout,
  package resources. API-only `frontend_dir=False` still works. Extracted resources are retained
  for the app lifespan. Invalid explicit settings produce actionable errors, not silent fallback.
- Add `mcda --version` and additive `/api/health.build` metadata (revision, dirty flag and served
  frontend index hash). Regenerate OpenAPI/TypeScript. Project schema, fingerprints, numerical
  result/record formats, reference fixtures and numerical engine/services remain unchanged.
- Check library writability and port availability before browser launch; open the browser after
  server readiness. This is startup validation, **not** a cross-process library lock.
- Hash-lock Python 3.12 runtime/dev/build environments with pip-tools 7.6.2, retaining the
  baseline numerical versions. Build tooling includes Hatchling 1.32.4, build 1.6.1 and editables
  0.5. Pipx 1.18.4 is used for isolated consumer checks. Frontend dependencies remain unchanged.
- Configure one Ubuntu 24.04 x86_64 / Python 3.12 / Node 26.12.1 CI job; no broad platform matrix.
  CI includes app/browser/distribution checks and manual/weekly mutations. It was first pushed and
  run on hosted runners on 2026-10-26 and passed on its third run (see below). Windows and
  additional Python versions are not claimed.

## Commands actually run and outcomes

Local environment: macOS 26.5.1 arm64, Python 3.12.15, Node 26.12.1, npm 11.20.0; native Chrome at
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. Existing numerical dependency
versions are retained; the previous baseline record has the version list. Build/lock tools were
installed into a local temporary directory, leaving the original `.venv` dependency set intact.

| Command / check | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 623 passed, one existing Starlette/httpx deprecation warning; final original-environment run 10.98 s |
| `<temporary tools environment>/bin/python -m pytest -q` after hash-locked dev/build install and editable install | 623 passed, same warning, 40.74 s; proves documented pinned setup works locally |
| `.venv/bin/ruff check src tests scripts hatch_build.py` | Passed |
| `.venv/bin/ruff format --check src tests scripts hatch_build.py` | Passed, 84 files |
| `.venv/bin/mypy` | Passed, 39 source files |
| `.venv/bin/python scripts/export_openapi.py --check` | Passed; additive health metadata generated with `scripts/export_openapi.py`, then `npm --prefix frontend run gen:types` |
| `.venv/bin/python scripts/acceptance_demo.py` | Passed, including fresh-process save/reopen |
| `.venv/bin/python scripts/acceptance_evidence.py <temporary directory>` | Passed, VC independent crossovers, contribution reconciliation, performance fixture reproduction and exact save/reopen |
| `npm --prefix frontend run check` | Passed: TypeScript, ESLint, generated types, 234 tests/24 files and production build |
| `MCDA_PYTHON="$PWD/.venv/bin/python" MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm --prefix frontend run test:e2e` | 67 passed in 1.6 min, disposable backend/store; required execution permission for localhost/browser |
| `<temporary tools environment>/bin/python scripts/build_release.py` | Passed: npm ci/build, direct wheel, sdist, extracted-sdist wheel without isolation/index, archive inspections and missing-GUI negative gate |
| `<temporary tools environment>/bin/python scripts/build_release.py --skip-frontend` | Passed for final source/lock/script updates after the successful frontend build; both wheel hashes match |
| `MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' <temporary tools environment>/bin/python scripts/smoke_install.py --browser --wheelhouse <temporary wheelhouse>` | Passed on final wheel hashes: both wheel routes and isolated pipx browser/HTTP/CLI workflows, export and fresh-process reopen |
| `.venv/bin/python scripts/mutation_check.py` | Passed: unmodified scratch baseline and 64/64 mutants killed |
| `git diff --check` and changed-document relative links | Passed; 103 relative file links across 10 checked documents resolve |

Lock generation and installation commands actually exercised:

```sh
# Initial tools bootstrap in a temporary venv (network permission required):
.venv/bin/python -m venv <temporary tools environment>
<temporary tools environment>/bin/python -m pip install build hatchling pip-tools pipx
# Pinned outputs were then generated with these locked tools:
<temporary tools environment>/bin/pip-compile --generate-hashes --strip-extras --no-emit-index-url --constraint requirements/baseline-py312.txt --extra api --output-file requirements/runtime-py312.txt pyproject.toml
<temporary tools environment>/bin/pip-compile --generate-hashes --strip-extras --no-emit-index-url --constraint requirements/baseline-py312.txt --extra dev --output-file requirements/dev-py312.txt pyproject.toml
<temporary tools environment>/bin/pip-compile --quiet --allow-unsafe --generate-hashes --strip-extras --no-emit-index-url --output-file requirements/build-py312.txt requirements/build.in
<temporary tools environment>/bin/python -m pip download --require-hashes --only-binary=:all: -r requirements/runtime-py312.txt -r requirements/build-py312.txt -r requirements/dev-py312.txt --dest <temporary wheelhouse>
<temporary tools environment>/bin/python -m pip install --no-index --find-links <temporary wheelhouse> --require-hashes -r requirements/build-py312.txt -r requirements/dev-py312.txt
<temporary tools environment>/bin/python -m pip install --no-deps --no-build-isolation -e '.[dev]'
<temporary tools environment>/bin/python -m pip check
```

The final build-lock correction was also downloaded and reinstalled with the same hash/offline
commands before retrying the editable install. No broken requirements were found.

## Failures diagnosed and resolved

- Initial tools download inside the sandbox failed DNS; retried with network execution permission.
- The build guard found `supplier_selection/README.md` absent; added documentation only.
- The first build-lock export omitted pip/setuptools as “unsafe”; regenerated with `--allow-unsafe`
  so fresh hashed installs pin those tools too.
- Clean editable installation found missing `editables`; added it to the build inputs/hash lock,
  reinstalled and verified the documented developer setup.
- One newly added occupied-port test initially failed because Rich wrapped the diagnostic line.
  The assertion now normalises whitespace and still requires the exact actionable wording.
- npm ci warned about an unapproved optional fsevents install script; installation/build passed
  with zero audit vulnerabilities. No allow-script policy or frontend lock was changed.

Workflow YAML also parsed successfully with `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "Workflow YAML parses"'`.
The installed GUI screenshot was visually inspected.

The earlier application baseline remains valid. Missing build tooling was a distribution gap and
is now addressed; it did not retroactively invalidate the recorded numerical/application tests.
No oracle, tolerance, fixture or numerical calculation was changed to get a pass.

## Remaining scope and limitations

Hosted Linux passed on the third hosted run, below: one Ubuntu 24.04 x86_64 job, not a broad
platform matrix. The two earlier failures were test-setup gaps, not application defects.

First hosted run (2026-10-26, commit `040407d`, Ubuntu 24.04): the pinned install succeeded and
649 of 651 Python tests passed. Two tests launched `serve --open`, which needs GUI assets, and the
workflow builds the frontend only in the following step, so both stopped at “No GUI assets found”
before reaching the port and ownership checks they test. They passed locally only because a
built `frontend/dist` existed. Both now supply their own minimal GUI folder through `--frontend`
and pass with and without a built checkout. The frontend, browser and distribution steps had not
yet run on hosted Linux.

Second hosted run (commit `9dc4ee3`): Python and contracts passed, and Frontend and browser
workflows passed, including the full Playwright suite on Ubuntu. Both distribution routes built and
installed, but the installed-GUI smoke could not launch Chromium: `smoke_install.py` isolates
`HOME` and `XDG_CACHE_HOME`, which also moved Playwright's default browser cache into the empty
temporary home. Local runs had passed only because `MCDA_CHROMIUM` named an installed Chrome. The
script now pins `PLAYWRIGHT_BROWSERS_PATH` to the caller's cache (unless already set) before
isolating, verified against Playwright's own executable-path resolution and a passing local smoke.

Third hosted run (hosted CI passed, private working repository, 26 October 2026 UTC;
commit `d886120`, Ubuntu 24.04 x86_64, Python 3.12, Node 26.12.1): every step passed. Hash-pinned
build/dev installation; 651 Python tests, Ruff check and format, mypy, OpenAPI freshness and both
acceptance scripts; frontend typecheck, lint, generated types, 269 unit tests in 29 files and
production build; 74 Playwright browser tests; direct wheel, sdist and the wheel rebuilt from the
extracted sdist; and the offline installed-GUI smoke on both wheel routes, the plain engine-only
wheel and isolated pipx. The mutation job runs only on manual dispatch or the weekly schedule and
has not yet run on Linux (68/68 locally).

Broader platform/Python coverage, signatures/native installers and publication are separate
decisions.
The actual smoke tests use POSIX venv layout on the scoped Mac/Linux paths. Pipx is installed in
an isolated temporary home, never into the user's normal application environment.

Next: essential library coordination and safe restore, then **D1 Visible model**, followed by
**D2 Connected coverage**. This package implements no recovery, canvas or numerical features.
The updated roadmap and canvas design record those boundaries and the real-user checkpoint.
