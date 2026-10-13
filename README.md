# ArcticDEM Workbench

ArcticDEM Workbench is a Python desktop application for finding repeat ArcticDEM observations, inspecting usable temporal coverage, computing DEMs of difference (DoDs), and comparing registration methods on persistent points and polygons. It records quality masks, accepted pair graphs, relative corrections and common evaluation support so that processing choices can be inspected together with the resulting height differences.

**Software version: 0.11.1. Public-source packaging revision: 11 October 2026.** The numerical application modules are byte-identical to the frozen 0.11.1 distribution. This revision adds public documentation, an open-source license, installation/build support, CI and verification entry points. It also corrects a stale 0.11.0 expectation in a regression test and includes the pilot CSV in built packages. It does not replace historical Batagay or controlled-experiment results.

## Requirements and installation

Use Python 3.12 on 64-bit Windows or Linux. The scientific stack is distributed as binary wheels. A 4-core CPU and 8 GB RAM are a practical starting point for small AOIs; resource needs increase with the raster grid and epoch count. Existing users with a working `arcticdem_dod` environment can reuse it for local verification. A clean environment is recommended for a new installation.

```bash
python -m venv .venv
# Windows CMD: .venv\Scripts\activate.bat
# Linux/macOS shell: source .venv/bin/activate
python -m pip install --only-binary=:all: -r requirements-lock.txt
python -m pip install --no-deps -e .
python -m arcticdem_workbench doctor
```

If a Conda Python interpreter is used, `environment.yml` supplies only Python, pip and Expat. Install the compiled scientific/Qt stack together from the wheel requirements. The supplied runtime initializes XML/DLL dependencies before Matplotlib and Qt. Do not mix Conda and pip copies of the same compiled geospatial or Qt libraries inside a new environment.

## Start and first example

```bash
python -m arcticdem_workbench gui --workspace work
python -m arcticdem_workbench demo --output work/synthetic_example
```

The GUI supports catalogue search, imported or drawn AOIs, candidate/common coverage, source quality checks, multi-epoch management, registration methods, fixed-coordinate point series, reusable polygons, network diagnostics and exported case reports. Maps support wheel zoom and left-button drag; drawing mode temporarily locks navigation. The synthetic CLI example is offline and creates its own inputs. See [User guide](docs/USER_GUIDE.md) and [Examples](examples/README.md).

## Recorded acceptance

The current application passed 104 regression tests on Linux and, subsequently, all 104 tests on Windows 10. The Windows offline example, common-support report, offscreen restoration and interactive saved-case session completed successfully on 13 October 2026 UTC. See [Windows evidence](validation/windows_20261013/README.md) and [current release status](RELEASE_STATUS.json). The interactive window opened and closed; comprehensive human visual inspection was not recorded. Remote GitHub CI still requires an actual run on the public commit.

The documentation and evidence update dated 13 October retains the frozen 0.11.1 application. Existing users who completed this acceptance do not need another local run for these documentation changes.

## Offline verification

```bash
python -I -X utf8 tools/verify_public_release.py
```

This checks source hashes, runs the regression suite, creates a separate synthetic joint-method and four-method acceptance case, verifies common support and saved-project restoration, and opens the saved case with Qt's offscreen platform. A result ZIP is printed. Add `--gui` for an interactive display check; close the window to complete the run. On Windows with the existing environment active, `RUN_PUBLIC_ACCEPTANCE.bat` performs this same bounded check. It does not install packages, download DEMs, or change existing research results.

## Build and test an installed distribution

```bash
python -m pip install -r requirements-dev.txt
python -m build --outdir work/dist
python -m pip install --no-deps --force-reinstall work/dist/arcticdem_workbench-0.11.1-py3-none-any.whl
python -I tools/wheel_smoke.py
```

The wheel check runs outside the source import path and verifies bundled assets, a known-change synthetic pipeline and GUI initialization. The CI workflow runs source verification and the installed-wheel check on Windows and Linux. A supplied workflow is not evidence that remote CI has executed: the public repository's Actions jobs must finish successfully before its release is marked tested.

## Scientific interpretation

DoD is later minus earlier elevation, in metres. Stable reference terrain must be selected on scientific grounds. Quality-valid overlap and catalogue footprint overlap are different quantities. Missing point values remain missing. Relative network closure evaluates consistency of independently fitted edges before adjustment; a closed network can retain node-consistent and common-mode errors. Low residuals and synthetic parameter recovery do not establish real-data absolute accuracy.

The internal Nuth–Kääb method is a historical implementation, not the xDEM or demcoreg implementation. The joint-gradient engine preserves its frozen controlled-experiment identity. No automatic scientific winner is selected. Detailed conventions and limitations are in [Methods and closure](docs/METHODS_AND_CLOSURE.md) and [Scientific scope](docs/SCIENTIFIC_SCOPE.md).

## Public contents and provenance

`arcticdem_workbench/` contains the complete application source and bundled catalogue/coastline assets. `tests/` contains the regression suite; `tools/` contains verification and execution utilities. `research/` preserves the available historical external-comparison sources and protocols with their original attribution. Those sources do not turn the current joint method into an executed external Batagay comparator. Original large DEMs and local workspaces are excluded; data-source and reproduction requirements are documented in [Research reproduction](research/README.md).

The paper plotting bundle regenerates six figures and five supplementary tables from saved records without registration or raster processing. It can be used locally for figure inspection and styling. Historical results retain their original software/version identity.

## License and citation

Original software is released under the MIT license. Natural Earth coastline data are public domain; PGC metadata and ArcticDEM-derived products retain their source attribution and license obligations. Dependency packages keep their own licenses. See [Third-party data](docs/THIRD_PARTY_DATA.md). `CITATION.cff` temporarily records the author label **Du et al.**, as specified by the maintainers. This label can be expanded when the complete attribution is confirmed. Add the actual repository and versioned-release links when available. No funding information is included in this repository.

## Companion paper figures

`RUN_RS_REPLOT.bat` regenerates six RS figures and five supplementary tables from frozen exports. See `research/rs_reproduction`. The distinct SoftwareX diagram is in `research/softwarex_figure`. See `docs/PUBLICATION_SCOPE.md` for the manuscripts and reproduction boundaries.
