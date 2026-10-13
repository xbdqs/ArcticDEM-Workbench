# Published-case benchmark protocol

The software should be validated across complementary signal regimes, not by presenting several visually attractive DoDs. Each benchmark must preserve the same AOI, target polygon, stable-terrain mask, independent validation mask, acquisition set and sample points across all registration methods.

## Benchmark families

1. **Glacier elevation and volume change** — a spatially distributed, mostly continuous signal. Compare elevation-change rates and volume change against a published geodetic result and, where available, ICESat-2 or airborne altimetry. Stable terrain must exclude glacier outlines plus a defensible buffer.
2. **Rock-glacier or periglacial slope** — a coupled horizontal-advection and vertical-change problem. DoD alone cannot establish activity. Compare the DoD pattern with published feature-tracking, GNSS or InSAR velocity and use off-landform stable terrain. Interpret positive/negative dipoles as possible slope advection until independently tested.
3. **Rapid mass movement or retrogressive thaw slump** — a large, localized signal. Compare mapped affected area, headwall retreat or displaced volume with a published event inventory or photogrammetric reconstruction. Pre/post acquisition timing must bracket the event.

## Acceptance criteria

- The catalogue query is not truncated, acquisition timestamps are explicit and no selected epochs share source images.
- Geometric common footprint and quality-valid common coverage are both reported.
- Raw, vertical-only and horizontal-plus-vertical methods use identical spatial objects.
- Pairwise fit samples and spatially separated validation samples are not reused as if independent.
- Registration parameters do not touch search bounds; failed or disconnected edges remain visible.
- Before/after median, NMAD, RMSE and 95th absolute residual quantile are reported for every edge.
- Pre-adjustment cycle closure is reported for redundant networks, with the explicit limitation that node-consistent and common-mode errors can close.
- Published values are compared using compatible dates, areas, vertical datums, units and uncertainty definitions. Agreement is not claimed from overlapping uncertainty intervals alone.
- A benchmark is classified as software verification unless its masks and reference observations are independently defensible.

## Registration-method benchmark

The `translation` method minimizes stable-terrain elevation residuals after bilinear sampling with a robust `soft_l1` objective. It estimates sampling dx, sampling dy and additive dz. It is not the Nuth–Kääb algorithm and is not labelled as such.

Version 0.3.0 adds Nuth–Kääb as a distinct iterative terrain-normalised slope/aspect implementation and a same-input comparison runner for vertical, direct translation and Nuth–Kääb methods. An established external implementation such as xDEM remains necessary for cross-validation. ICP is useful as an additional sensitivity method when terrain geometry supports it, but no method should be selected solely because it minimizes training residuals. Method choice should be based on spatial holdout diagnostics, parameter plausibility, coverage loss, closure, and independent reference evidence.

`demcoreg` is an important methodological and software reference, but direct dependency on its older environment should not be imposed on the Windows desktop application. Reproducing a documented algorithm or using a maintained optional backend is preferable to silently calling the current robust translation “Nuth–Kääb.”

## Published-case entry points (0.7.0)

The desktop tab **7 Published cases** creates versioned pilot workspaces for
Batagay (thaw slump), Karrat (rock avalanche) and Vavilov (glacier change).
See `PUBLISHED_CASES_CN.md` and the packaged `assets/published_cases.json` for
the exact primary references, coordinate provenance and measurement definitions.
These are candidates, not completed benchmarks. Their rectangles are Workbench
query windows, not published target or stable-terrain outlines. No reference
volume is prefilled. Freeze actual target, fit and validation regions plus
source dates before comparing methods. Shared source data must be disclosed
when assessing whether a literature comparison is externally independent.


## Executable controlled benchmarks (0.8.0)

The offline Scientific Validation Suite v0.1 now implements known analytic
translation recovery, change preservation, noise/outliers, missing coverage,
unmodelled tilt, flat-terrain identifiability and inadequate-support cases.
See `SCIENTIFIC_VALIDATION_CN.md` for fixed masks, prespecified checks, exact
inputs and output definitions. This is software verification; the published
case and external-implementation benchmarks above remain outstanding.
