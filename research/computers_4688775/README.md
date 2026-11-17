# Computers manuscript 4688775 — public, limited-scope reproduction

This folder accompanies the software paper **ArcticDEM Workbench for Traceable Multitemporal Elevation Change Analysis**. It contains **only an author-selected subset** of synthetic-case inputs and non-spatial timing records. It is not the complete Kinnikinnick research dataset.

## Software version and identities

- Source software: **ArcticDEM Workbench v0.11.1**.
- Fixed software-source commit: `d9f665fcfb98ef0694fff2de4b74617b6eb0ff3d`.
- This paper-materials folder may be added in a later commit; **cite that later repository commit separately**. Adding reproduction records does not change the algorithm tested in v0.11.1.

## Files included

- `inputs/figure06_original_rasters/`: two **synthetic acceptance-case** 256 × 256 GeoTIFF masks from previously saved verification results (64,496 common-valid cells; 10,523 validation cells). These do **not** represent the real Kinnikinnick masks.
- `inputs/performance/`: non-spatial timing and process-resource records from 18 four-method runs and three targeted runs. The pair-timing CSV is privacy-reduced to timing and convergence columns; it contains no fitted spatial parameters or elevation-residual statistics.
- `inputs/table_snapshots/`: saved manuscript Table 8 reference values used for exact formatting checks.
- `scripts/`: independent code to render Figure 6 and recompute Tables 8 and 9 using the data above.
- `PUBLIC_FILE_SHA256.json`: SHA-256/byte-count inventory of the files offered for public upload.

## Run locally

With a Python environment providing `numpy`, `matplotlib`, and `rasterio`, from this directory run:

```bash
python scripts/figure_06.py
python scripts/table_08.py
python scripts/table_09.py
```

Outputs are placed in `regenerated/figures/` and `regenerated/tables/`. Figure 6 can be exported as PNG, PDF, and SVG. These commands **redraw from archived masks and reanalyze archived performance logs**; they do not re-run the original ArcticDEM registration workflow.

## Scope and limitations

**The author has chosen not to publish Kinnikinnick-derived numerical arrays.** Consequently, the real-case source DEMs, quality rasters, published comparison products, original/derived per-pixel arrays, scar boundaries, source rasters, and associated local-only figure/table source package are not in this folder. In particular, Figures 8–11 and Tables 5–6 cannot be numerically regenerated from this public folder alone. Please consult the published source-data providers and the article's Data Availability Statement for access constraints.

The 18-run records measure full **command-line analysis and result generation**, not GUI use or downloads. The three-run targeted experiment reports actual network-solve calls, *in-memory* ndarray intersection, and Windows **peak working set (RSS proxy)**. Intersections exclude raster disk input/output, and memory records reflect whole-process peaks. Neither dataset establishes absolute surface-elevation accuracy or scaling beyond the tested configuration.

The Python code is based on the original application and saved author analysis records. No new software release, DOI deposit, or public hosting of restricted raster data is implied.
