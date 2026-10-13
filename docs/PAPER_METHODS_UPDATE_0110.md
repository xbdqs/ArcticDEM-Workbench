# Manuscript update after desktop integration

Date: 10 October 2026. This note updates the earlier draft's statement that the joint-gradient candidate was available only as an independent benchmark script. Windows release acceptance remains pending user-side confirmation; real-case registration and external accuracy are not claimed here.

## Replacement text for the implementation subsection

The joint-gradient candidate is provided as an optional registration method in the Workbench 0.11.0 source release. Its numerical engine is retained byte-for-byte from the frozen RUN24 implementation, with a source-hash check before fitting. A production adapter establishes finite fitting support over the specified horizontal search domain, applies the reference-gradient eligibility rule and selects up to 12,000 fitting cells using a fixed seed. The adapter also enforces minimum spatial holdout support before and after alignment. The model, robust loss, Jacobian and iteration policy of the frozen engine are unchanged. Engine provenance and sampling metadata are recorded alongside registration diagnostics. Desktop input eligibility and support selection are documented separately from the controlled experiment protocol.

The method is available for individual pairs, multi-epoch registration networks and four-method comparison, and its identifier is retained in saved projects and restored on reopening. The legacy internal Nuth–Kääb identifier remains supported for historical reproduction, with explicit limitations in the interface and output warnings. The direct robust translation comparator is also retained with its controlled failure evidence disclosed. No baseline is silently relabelled as the new method.

Comparison mode reports all four method outcomes, including failures. Its initial display follows a fixed order of completed methods rather than selecting the lowest per-method residual. Per-method residuals can use different finite support, whereas the exported case report computes final-stack statistics on shared valid support. The displayed result is therefore a navigation choice, not an automatic accuracy ranking or scientific recommendation. The initial application method remains unregistered differencing.

## Evidence available now

- RUN24 remains the frozen controlled transfer evidence: four selected windows, nine prescribed conditions and one seed per condition. It is not rerun or reclassified as a real-data accuracy test.
- The adapter reproduces the frozen engine's parameter estimates in the targeted same-input check. A synthetic known change is retained through the pipeline.
- Developer regression, project restoration, four-method common-support export and offscreen GUI initialization are documented in `V0110_VALIDATION_CN.md`.
- The bounded user-side acceptance script records actual runtime versions and Qt platform, preserves previous outputs and collects a diagnostic ZIP. A screenshot or initialization status does not automatically certify a user's visual review.

## Items still required for a complete manuscript

A reviewed real main-case spatial design and its results; clearly defined reference-data relationships and limitations; final release archive/availability and license statements. The controlled 0.087 m parameter error must not be described as real ArcticDEM elevation accuracy. Public code release and a completed externally validated real case are not implied by this integration note.
