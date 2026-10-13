# Historical paper evidence and sources

This folder preserves the available historical experiment sources and compact protocols supplied with the paper closeout. The complete desktop application is in `arcticdem_workbench/`. Historical research sources are separate from the application's dependencies and normal verification.

| Material | Identity and use | Reproduction limit |
| --- | --- | --- |
| `paper_protocols/run24/` | Frozen registration source, joint-gradient candidate, perturbation protocol and audited controlled-recovery records | Original terrain DEM windows and the full historical RUN24 orchestration archive are not bundled here. The production adapter is not an undocumented substitute for the historical runner. |
| `batagay_external/` | Available executed external-comparison runner, worker, runtime initialization, reporting code and xDEM adapter | Full rerun needs the four original epoch inputs, masks and historical internal software. The executed external environment used xDEM 0.2.3 and geoutils 0.2.5; these are not current desktop dependencies. |
| `paper_protocols/batagay_four_epoch/` | Source identities, fixed points/polygons and saved four-epoch summary | Large rasters are excluded. Recorded paths describe the original run, not portable download instructions. |
| `paper_protocols/batagay_external/` | Frozen external protocol, epoch identities, saved external summary and fixed objects | Does not claim that the current joint-gradient method was evaluated against xDEM on this case. |
| `paper_protocols/batagay_common_graph/` | Original/common graph descriptions, identical-support statistics, contrast summaries and fixed point series | Saved records can be inspected or replotted. Pixelwise recomputation needs original accepted pair estimates, masks, rasters and the historical graph-analysis runner, which are not all in this compact package. |

Historical Python sources retain their original bytes. Hashes and relationship to the source closeout are in `docs/SOURCE_PROVENANCE.json`. Machine-specific environment probes and working-directory dumps are omitted from public compact material; scientific protocols and result records are retained.

Use `python -I tools/verify_public_release.py` for a fully bundled offline demonstration of the current software. It generates DEMs, checks a known −8 m change, compares four methods on shared support and reopens a saved project. This verifies software behaviour without replacing the manuscript's historical experiments.

The separate `ArcticDEM_Paper_Reproduction_20261011` bundle regenerates all manuscript figures and supplementary tables from frozen saved records. No alignment is repeated. Local figure reproduction is independent of the desktop CI.

ArcticDEM products and PGC metadata retain their original attribution requirements. Original Workbench research code follows the MIT license. External packages keep their own licenses. Retain full original workspaces for scientific audit and, where appropriate, share them as a separate research archive. A summary record alone does not establish complete pixelwise reproduction.
