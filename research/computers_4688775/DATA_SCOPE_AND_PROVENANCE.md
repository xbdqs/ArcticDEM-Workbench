# Data scope, provenance, and publication boundaries

## Published here

1. **Synthetic common-support masks.** The two GeoTIFFs are from the saved deterministic synthetic software acceptance case, not real satellite observations. Stored grid 256 × 256, EPSG:3413, nominal resolution 2 m. See `scripts/figure_06.py` for an auditable pixel-count check.
2. **Local real-case computational timings.** The 18-run full-script timing CSV and 3-run targeted resource measurements support the manuscript's performance sections. Individual pair-records are deliberately reduced to non-spatial fitting-time and convergence fields. Timings were observed on the author's local Windows machine; they are not a universal hardware performance claim.

## Intentionally not released

The author elected **not** to distribute any Kinnikinnick-derived per-pixel numerical arrays or third-party source products. Not included: four-epoch ArcticDEM DEM strips; native bitmasks and matchtags; any publication comparison raster/data product; `comparison_data.npz`; published footprint/scar vectors; source-derived spatial arrays and unpublished local-only scientific figure/table archives; unredacted local run logs; manuscript drafts, review correspondence, contact details and personal identifiers.

This public subset does **not** reproduce the real-case per-pixel cross-product analysis for Figures 8–11 and Tables 5–6. The manuscript must state this limitation; do not describe these files as a complete public reproduction of the Kinnikinnick case.

## Attribution for external sources described by the article

- Polar Geospatial Center, University of Minnesota, **ArcticDEM**: https://www.pgc.umn.edu/data/arcticdem/
- Dai et al. (2024), published Kinnikinnick comparison data (source referenced, **not re-hosted here**): https://doi.org/10.17632/6dy5jnymww.1

Links above identify externally provided data. The linked products are **not** redistributed in this public folder. No new license is asserted over third-party material.

## Release/version statement

The application version remains 0.11.1 at commit `d9f665fcfb98ef0694fff2de4b74617b6eb0ff3d`. After publishing the present folder, independently record its repository commit SHA and pin that SHA in the article. Until that action, do not claim this folder is available online.
