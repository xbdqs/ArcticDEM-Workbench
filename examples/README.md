# Offline synthetic example

From the repository root or an installed application:

```bash
python -m arcticdem_workbench demo --output work/synthetic_example
```

The command generates four dated 2 m DEMs, a stable-terrain mask, prescribed vertical biases and a protected lowering region, then writes a runnable configuration and analysis results. It creates local inputs rather than downloading observations. The tool retains missing-value and quality-mask semantics and produces pair DoDs, an epoch stack and network diagnostics.

For the public acceptance example, run `python -I tools/verify_public_release.py`. Its three-epoch joint case includes a known −8 m change, and its two-epoch four-method report uses common pixels and a fixed point. The result ZIP contains the exact generated inputs, saved configuration, reports and environment record. This provides a reviewer example without redistributing large ArcticDEM rasters.

Use the printed result directory in the GUI's Open results control. Add `--gui` to public verification to restore the generated project interactively. Close the window to complete the acceptance record.
