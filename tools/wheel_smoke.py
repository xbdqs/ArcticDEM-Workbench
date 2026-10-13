"""Run with python -I after installing a built wheel, outside the source import path."""
from pathlib import Path
import importlib.resources as resources
import json
import os
import sys
import tempfile


def main():
    import arcticdem_workbench as package
    if not Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError('Expected an installed wheel, not a source-tree import.')
    from arcticdem_workbench.windows_runtime import prepare_runtime
    prepare_runtime()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    for name in ('assets/ne_110m_coastline.geojson', 'assets/published_cases.json',
                 'assets/pilots/batagay_query.json', 'assets/pilots/batagay_query.csv',
                 'assets/pilots/batagay_selection.json', 'assets/pilots/batagay_coverage_reference.json'):
        data = resources.files(package).joinpath(name).read_bytes()
        if not data:
            raise RuntimeError('Missing package data: ' + name)
    from arcticdem_workbench.demo import create_demo
    from arcticdem_workbench.pipeline import run
    from arcticdem_workbench.gui import Window
    from PySide6.QtWidgets import QApplication
    from arcticdem_workbench.cases import load_cases
    import numpy as np
    import rasterio
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='arcticdem_wheel_') as temporary:
        root = Path(temporary)
        cfg = create_demo(root / 'inputs')
        cfg.update(method='joint_gradient', output=str(root / 'result'))
        cfg['epochs'] = cfg['epochs'][:3]
        report = run(cfg, log=lambda message: None)
        with rasterio.open(root / 'result/epoch_stack.tif') as source:
            dh = source.read(3, masked=True).filled(np.nan) - source.read(1, masked=True).filled(np.nan)
        recovered = float(np.nanmedian(dh[110:145, 110:145]))
        assert abs(recovered + 8) < .12, recovered
        window = Window(root / 'gui_work')
        window.load_results(root / 'result')
        window.show(); app.processEvents()
        assert window.tabs.count() == 7
        assert package.__version__ in window.windowTitle()
        result = {'status': 'passed', 'version': package.__version__,
                  'installed_wheel': True, 'package_file': str(Path(package.__file__).resolve()),
                  'assets_checked': 6, 'case_templates': len(load_cases()),
                  'synthetic_known_change_m': -8, 'recovered_change_m': recovered,
                  'pipeline_status': report['status'], 'qt_platform': app.platformName(),
                  'human_visual_review': 'not_recorded'}
        window.deleteLater(); app.processEvents()
        print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
