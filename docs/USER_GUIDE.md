# User guide

## Inputs and spatial objects

Catalogue searches accept WGS84 west/south/east/north bounds and acquisition dates. Imported or drawn GeoJSON polygons remain the analysis objects when a bounding rectangle is needed for retrieval. Save and export AOIs to repeat the same study area. Catalogue footprints describe candidate coverage; a source bitmask and matchtag determine quality-valid elevation support. Inspect joint valid coverage before choosing a temporal network.

Local inputs require dated DEMs, metres, compatible vertical references and explicit quality assets where available. Supply a stable-terrain fit mask before registration. A withheld validation mask or spatial-block split provides internal diagnostics; its scientific stability still requires justification. Avoid moving saved workspaces solely to make the directory name match a newer software version, because saved projects can contain absolute input paths.

## Processing choices

Choose raw differencing, vertical correction, direct translation, historical internal Nuth–Kääb, or joint-gradient translation. A four-method comparison includes the four registered methods. The production default remains raw differencing. Set the common grid resolution, pair network, fit mask, withheld evaluation design and shift bounds before processing. Rejected fits remain recorded. A disconnected graph cannot provide one common anchored multi-epoch solution.

The sampling convention is `aligned[r,c] = moving[r-dy/res, c+dx/res] + dz`; the horizontal values are sampling offsets. DoD is later minus earlier height. Native estimator parameters require a stated conversion before cross-implementation comparison. A stable fit mask protects prescribed changes only when those changes and appropriate buffers are excluded from fitting.

## Results and reports

Results include registered epoch stacks, pair DoDs, pair-fit diagnostics, accepted networks and closure diagnostics. Case reports export persistent points and polygons. Point extraction uses the same containing grid cell for each method and preserves unavailable values. Regions use the documented valid support and ground-area correction. Cross-method comparison reports intersect final valid pixels across methods and epochs, and record fit/evaluation membership differences.

Load saved results or projects to inspect the method dropdown, DoD maps, fixed-point series and common-support report. Wheel zoom and left-button drag navigate maps; select a draw tool to create an AOI or stable polygon. Finish/cancel drawing before navigation. Export spatial objects and keep identifiers unchanged when comparing methods. Reports describe method differences and internal diagnostics; do not interpret a difference between products as error against truth.

## Typical command-line use

```bash
python -m arcticdem_workbench --help
python -m arcticdem_workbench doctor --output work/environment.json
python -m arcticdem_workbench search --bbox 15.47 78.195 15.50 78.205 --start 2016-01-01 --output work/query.json
python -m arcticdem_workbench run path/to/job.json
python -m arcticdem_workbench report path/to/result --output work/report --objects path/to/objects.geojson
```

Search/download commands need Internet access and retrieve source metadata/data. Offline verification and synthetic examples do not. Installation errors, source-check failures and registration rejections are reported separately. Preserve the printed verification ZIP when requesting support.
