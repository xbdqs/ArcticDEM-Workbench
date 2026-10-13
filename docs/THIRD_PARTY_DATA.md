# Third-party data and software

The regional coastlines are from Natural Earth, `ne_110m_coastline.geojson`, accessed 2026-09-10. Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_coastline.geojson . Natural Earth states its map data are public domain: https://www.naturalearthdata.com/about/terms-of-use/ . Coastlines are for regional context, not precise local shoreline interpretation. No national borders are drawn.

ArcticDEM observations and metadata are provided by the Polar Geospatial Center. Each query snapshot preserves original STAC metadata, assets, collection and license fields. The accessed items declare CC-BY-4.0. Follow PGC's current attribution instructions when publishing derivatives: https://www.pgc.umn.edu/data/arcticdem/ . The included real-data smoke example is an engineering check; it does not validate geophysical changes.

Numerical and desktop dependencies retain their own licenses: NumPy, SciPy, Rasterio/GDAL, affine, pyproj/PROJ, Shapely/GEOS, Matplotlib and Qt/PySide6. They are installed from dependency distributions; their source code is not copied into this software archive. Review the Qt/PySide6 distribution requirements before preparing a standalone executable for public redistribution.

No publication, repository creation or external deployment is performed by the supplied scripts.

## Published-case catalogue (0.7.0)

`arcticdem_workbench/assets/published_cases.json` contains original Workbench
planning notes, bibliographic links, documented site coordinates and newly
chosen pilot query rectangles. It does not redistribute article figures, full
papers, published target polygons or third-party DEMs. The primary references
and sections supporting site locations are listed in each record and in
`PUBLISHED_CASES_CN.md`. A pilot rectangle is not a published research boundary.
