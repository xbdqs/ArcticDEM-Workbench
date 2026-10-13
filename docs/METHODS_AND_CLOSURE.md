# Multi-epoch DoD and translation-network closure

## What is measured

All grids are horizontal surface-height representations. A difference is defined as later minus earlier:

\[
d_{ij}(x,y)=z_j(x,y)-z_i(x,y).
\]

For three DEMs on the same grid and common valid support,

\[
d_{ij}+d_{jk}-d_{ik}=0
\]

is an algebraic identity, including when the DEMs contain errors. It therefore does not independently validate a DoD. Numerical or masking inconsistencies can break the identity, but that is a processing-consistency issue.

InSAR phase-closure methods can exploit pair-specific interferogram processing and unwrapping inconsistencies. The present software borrows graph redundancy and cycle consistency; it does not process SAR phase, perform phase unwrapping, assume 2π ambiguities, or treat all closure discrepancies as errors of a known edge. MintPy's implementation is a reference for the InSAR distinction, not reused code.

## Independently fitted edge observations

For each selected pair, the software independently estimates a translation on user-defined stable terrain:

\[
z_j(x+s_x,y+s_y)+s_z \approx z_i(x,y).
\]

The vector \(\hat{\mathbf{s}}_{ij}=(s_x,s_y,s_z)\) contains **sampling-coordinate** shifts in EPSG:3413 metres plus an additive vertical correction. It is not a physical ground-displacement vector. In a north-up raster, positive map Y is negative array-row shift. The software records that conversion explicitly.

Vertical-only fitting uses the median residual. Three-parameter fitting minimizes a soft-L1 loss of bilinearly interpolated height residuals on the fitting mask, with bounded horizontal offsets. Finite-data support is eroded over the full search radius before optimization. Up to 30,000 fitting pixels are reproducibly sampled. A rank/condition check rejects poorly constrained horizontal fits. The independent fitting calculations still share DEM inputs and can have correlated errors.

The separate `nuth_kaab` option iteratively normalises residual elevation by terrain slope and fits the resulting aspect sinusoid with a robust loss. Gradient components are used internally to avoid ambiguity between mathematical and geographic aspect conventions. Median vertical correction and horizontal correction are accumulated, bounded and convergence-checked; the moving DEM is resampled once using the final transform. Flat terrain and poorly distributed stable-slope aspects are rejected. This implementation must still be cross-checked against independent implementations and real control data before accuracy claims.

Comparison mode runs vertical-only, direct three-parameter translation and Nuth–Kääb with identical input DEMs, AOI, masks, network and numerical limits. Its ranking by mean spatial-holdout NMAD is explicitly diagnostic: it does not override physical plausibility, external validation, coverage loss or the user's final method choice.

For pure translations, composition is additive. An independently observed triangle closure is:

\[
\mathbf{c}_{ijk}=\hat{\mathbf{s}}_{ij}+\hat{\mathbf{s}}_{jk}-\hat{\mathbf{s}}_{ik}.
\]

Both components and the three-dimensional norm are retained before adjustment. The norm is descriptive, not a calibrated probability or significance test. Rotations and other transforms would require proper transform composition; simply summing their parameters would not be valid.

A spanning tree defines a fundamental cycle basis. Every non-tree edge adds one independent cycle. For a connected graph with \(n\) nodes and \(m\) edges, the cycle rank is \(m-n+1\). Reporting all triangles alone would miss cycles in a graph without triangles and could overstate the number of independent constraints.

## Network adjustment

Node sampling offsets \(\mathbf{q}_i\) satisfy the observation model

\[
\hat{\mathbf{s}}_{ij}=\mathbf{q}_j-\mathbf{q}_i+\boldsymbol{\epsilon}_{ij}.
\]

The initial implementation fixes \(\mathbf{q}_0=\mathbf{0}\) and minimizes

\[
\sum_{(i,j)\in E}\left\|\mathbf{q}_j-\mathbf{q}_i-\hat{\mathbf{s}}_{ij}\right\|^2.
\]

This is equal-edge-weight least squares. It is not a full generalized least-squares uncertainty model: shared DEMs, source imagery, spatial sampling and residual patterns produce dependencies that are not currently modelled. Pair validation scores are retained as diagnostics rather than silently interpreted as calibrated edge variances. No automatic edge removal is performed. A failing loop cannot uniquely identify its failing edge without extra information.

The adjusted node shifts are applied once to the common-grid inputs. Original pre-registration differences and independent edge measurements are retained. Post-adjustment closure follows from the node-potential model and is not reported as an accuracy improvement.

Closure cannot detect all errors. For example, arbitrary node biases \(b_i\) produce edge differences \(b_j-b_i\), which close perfectly. Common-mode errors can also be invisible. Stable references, image lineage, seasonal comparability and external observations remain necessary.

## Temporal and uncertainty support

The software rejects repeated acquisition days and shared source image IDs in a selected analysis stack. This prevents obvious pseudoreplication; it does not prove statistical independence. Cross-track products are excluded by default in catalogue queries and their start/end times are preserved when included. A nominal date is insufficient to resolve change within a multi-day stereo interval.

For each pixel, the software reports valid epoch count and actual observation span. A descriptive OLS rate is computed only with at least three valid observations spanning at least one year. Seasonal and nonlinear modelling, event-time inference and formal trend significance are outside this release.

Registration and checking use spatially disjoint masks. With no user-supplied validation mask, held-out spatial blocks are selected deterministically from the stable mask; a small guard separates fitting from held-out blocks. This internal split does not remove all spatial dependence. Minimum pixel/block counts are software safeguards, not universal statistical sufficiency criteria.

Where sufficient held-out terrain exists, an exploratory threshold is the empirical 95th percentile of absolute held-out residuals. This retains residual bias in the threshold but does not establish transferability to changing slopes or different surface types. It is not a map-wide false-positive guarantee and does not specify detection power. Spatially heterogeneous uncertainty, correlation-aware volume propagation and independent calibration are required before publication-grade quantitative claims.

Net volume uses all valid differences, not only threshold-exceeding pixels. Pixel area is approximated by projected grid-cell area divided by the local projection areal scale at the cell centre. No constant 4 m² ground-area assumption is made for EPSG:3413. No volume uncertainty interval is generated in this release.

## Sources and implementation references

- PGC ArcticDEM products: https://www.pgc.umn.edu/data/arcticdem/
- PGC product and mask definitions: https://www.pgc.umn.edu/guides/stereo-derived-elevation-models/pgc-dem-products-arcticdem-rema-and-earthdem/
- PGC STAC access: https://www.pgc.umn.edu/guides/stereo-derived-elevation-models/stac-access-static-and-dynamic-api/
- PGC dynamic collection: https://stac.pgc.umn.edu/api/v1/collections/arcticdem-strips-s2s041-2m
- Nuth and Kääb (2011), reference background on DEM co-registration: https://doi.org/10.5194/tc-5-271-2011
- xDEM co-registration method descriptions: https://xdem.readthedocs.io/en/stable/coregistration.html
- Hugonnet et al. (2022), uncertainty from stable terrain: https://doi.org/10.1109/JSTARS.2022.3188922
- MintPy phase-closure implementation: https://github.com/insarlab/MintPy/blob/main/src/mintpy/unwrap_error_phase_closure.py
- Rasterio reprojection documentation: https://rasterio.readthedocs.io/en/stable/topics/reproject.html

These are method and data references, not claims that the first-release implementation reproduces every referenced algorithm. The 3D optimizer is an explicitly documented residual-minimization implementation, not the named Nuth–Kääb algorithm.
