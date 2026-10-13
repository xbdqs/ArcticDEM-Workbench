# Verification and release boundaries

The source inventory records public source files by size and SHA-256. Linux preparation records are in `validation/public_20261011/`; the completed Windows run is in `validation/windows_20261013/`. The latter passed 104 tests, synthetic processing and offscreen/interactive project restoration. These logs are not source inputs. A workflow file alone does not imply that GitHub Actions has passed.

## One bounded local check

```bash
python -I -X utf8 tools/verify_public_release.py
```

With a working Windows Python 3.12 environment active, `RUN_PUBLIC_ACCEPTANCE.bat` adds a visible GUI session. Inspect the restored method, map and saved report, then close the GUI. The script writes a new `work/public_acceptance/` directory and prints an `UPLOAD_PUBLIC_ACCEPTANCE_*.zip` path. It does not install packages, retrieve ArcticDEM data, modify another version's workspace or repeat a real-data experiment. Retain that ZIP and the console output if it fails.

Existing regression tests cover catalogue pagination and range requests; masks and raster support; persistent geometry/projects; controlled registration and network blind spots; coverage, reports and desktop interaction. A separate synthetic acceptance check verifies a known change, three-epoch joint network, four-method common-support report and saved-project restoration. Offscreen Qt startup is recorded separately from a human inspection of the visible GUI.

## Installed distribution

```bash
python -m pip install --only-binary=:all: -r requirements-dev.txt
python -m build --outdir work/dist
python -m pip install --no-deps --force-reinstall work/dist/arcticdem_workbench-0.11.1-py3-none-any.whl
python -I tools/wheel_smoke.py
```

The wheel check imports the installed package outside the source import path. It verifies six assets, including the pilot CSV, and exercises a known-change pipeline plus GUI startup. This detects omissions that source-tree tests can miss. The CI workflow runs these checks on Windows and Linux and preserves artifacts.

## Acceptance endpoint

Local acceptance for this application is complete. The interactive Windows session opened and closed, although comprehensive human visual review was not recorded. Complete the public release after both GitHub CI jobs pass on its intended commit; existing users do not need to repeat local acceptance for documentation-only updates. Repeat a check only after failure or a relevant code/dependency change. Keep historical controlled and Batagay results frozen. Software acceptance does not establish real-data absolute accuracy.
