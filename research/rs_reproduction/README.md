# Remote Sensing manuscript reproduction

Run `python reproduce_rs.py --output output/my_RS_figures --dpi 300 --font-size 11` or `RUN_RS_REPLOT.bat` in the existing working Python environment. Outputs include six PNG/SVG/PDF figures, five supplementary tables and machine-readable checks. See README_CN.md and FIGURE_TABLE_INDEX.md for exact mappings.

The original reproduce_paper.py is retained unchanged as the four-result-figure numerical renderer. RS layout code uses the same frozen values; old Figure_1–4 source export filenames map to RS Figures 3–6. INPUT_MANIFEST.json checks original values; RS_SPATIAL_MANIFEST.json checks geographic objects. No registration, raster processing or data download is repeated.

The checked publication outputs are rs_checked_outputs/. The desktop application is distributed separately; the parent guide and manuscript supplement S5 identify additional historical raw data and orchestration needed for complete scientific reproduction. Figure regeneration does not provide those prerequisites.
