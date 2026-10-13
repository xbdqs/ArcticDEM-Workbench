"""Saved pre-registration coverage inspection, separate from DoD results."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import shutil
import numpy as np
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QFileDialog,QPushButton


class CoverageMixin:
    def build_coverage_controls(self,layout):
        self.last_coverage_dir=None
        row=QHBoxLayout()
        row.addWidget(self.button('Check valid coverage before registration',self.check_coverage))
        row.addWidget(self.button('View saved coverage…',self.view_coverage))
        row.addWidget(self.button('Open coverage report',self.open_coverage_report))
        row.addWidget(self.button('Load coverage folder…',self.load_coverage_folder))
        layout.addLayout(row)
        self.coverage_info=QLabel('Coverage not checked. Import 2–12 distinct dates, then inspect quality-valid overlap before fitting.')
        self.coverage_info.setWordWrap(True); layout.addWidget(self.coverage_info)

    def check_coverage(self):
        if self.case_busy(): return
        cfg=self.guard(self.job)
        if not cfg: return
        from .coverage import inspect_coverage
        output=self.workspace/'coverage'/datetime.now().strftime('check_%Y%m%d_%H%M%S_%f')
        cfg['output']=str(output)
        self.start('Checking quality-valid temporal coverage…',lambda log,cancel:inspect_coverage(cfg,output,log,cancel),self.coverage_finished)

    def coverage_finished(self,result):
        self.last_coverage_dir=Path(result['output']); self.refresh_coverage_info()
        self.log('Coverage saved. Inspect count and pair masks before selecting registration: '+str(self.last_coverage_dir))

    def refresh_coverage_info(self):
        p=self.last_coverage_dir/'coverage.json' if self.last_coverage_dir else None
        if not p or not p.is_file():
            self.coverage_info.setText('No saved coverage linked to this case.'); return
        try:
            d=json.loads(p.read_text(encoding='utf-8'))
            self.coverage_info.setText(f"Saved pre-registration check: {d['epoch_count']} dates; ≥2 dates {d['at_least_two']['fraction_of_aoi']:.2%}; all dates {d['all_epochs']['fraction_of_aoi']:.2%} of AOI. Recheck after changing inputs, AOI or quality settings.")
        except (KeyError,ValueError,OSError): self.coverage_info.setText('Saved coverage unreadable: '+str(p))

    def load_coverage_folder(self):
        if self.case_busy(): return
        p=QFileDialog.getExistingDirectory(self,'Folder containing coverage.json',str(self.workspace))
        if not p: return
        def load():
            self.coverage_document(Path(p)); self.last_coverage_dir=Path(p); self.refresh_coverage_info()
        self.guard(load)

    def coverage_document(self,folder):
        if not folder: raise ValueError('Run a coverage check or load a completed coverage folder first.')
        if json.loads((folder/'status.json').read_text(encoding='utf-8'))['status']!='completed':
            raise ValueError('Coverage check is incomplete; inspect status.json.')
        doc=json.loads((folder/'coverage.json').read_text(encoding='utf-8'))
        if doc.get('stage')!='quality_screened_before_registration': raise ValueError('Not a pre-registration coverage report.')
        return doc

    def open_coverage_report(self):
        def open_report():
            self.coverage_document(self.last_coverage_dir)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_coverage_dir/'report.html')))
        self.guard(open_report)

    def view_coverage(self):
        def show():
            from .gui import CanvasPanel
            from .plots import read_preview
            from .coverage import pair_mask
            from .raster import write_raster
            from matplotlib.colors import ListedColormap,BoundaryNorm
            from matplotlib import colormaps
            folder=self.last_coverage_dir; doc=self.coverage_document(folder)
            dialog=QDialog(self); dialog.setWindowTitle('Quality-valid coverage before registration'); dialog.resize(1080,830)
            layout=QVBoxLayout(dialog)
            note=QLabel('Saved quality-screened coverage before registration. Final support may differ. Left drag: pan; wheel: zoom. Export retains full resolution.')
            note.setWordWrap(True); layout.addWidget(note)
            row=QHBoxLayout(); layer=QComboBox(); row.addWidget(layer,1)
            export=QPushButton('Export displayed mask / raster…'); row.addWidget(export); layout.addLayout(row)
            layer.addItem('Number of quality-valid acquisition dates','valid_date_count.tif')
            layer.addItem('Observed temporal span (years, ≥2 dates)','observed_span_years.tif')
            layer.addItem('Common pixels of every selected date','all_epochs_valid_mask.tif')
            for pair in doc['pair_statistics']:
                layer.addItem(pair['start'][:10]+' → '+pair['end'][:10]+f" · {pair['fraction_of_aoi']:.2%} of AOI",(pair['i'],pair['j']))
            panel=CanvasPanel(); layout.addWidget(panel,1)
            def draw():
                value=layer.currentData(); panel.fig.clear(); panel.ax=panel.fig.add_subplot(111)
                if isinstance(value,(tuple,list)):
                    data,grid=pair_mask(folder,*value); a=np.ma.masked_equal(data,255)
                    extent=[grid.bounds[0],grid.bounds[2],grid.bounds[1],grid.bounds[3]]; crs=str(grid.crs)
                else: a,extent,crs=read_preview(folder/value)
                if value=='valid_date_count.tif':
                    n=doc['epoch_count']; cm=colormaps['viridis'].resampled(n+1)
                    im=panel.ax.imshow(a,extent=extent,cmap=cm,norm=BoundaryNorm(np.arange(-.5,n+1.5),n+1),interpolation='nearest')
                    panel.fig.colorbar(im,ax=panel.ax,ticks=range(n+1),label='Valid acquisition dates')
                elif value=='observed_span_years.tif':
                    im=panel.ax.imshow(a,extent=extent,cmap='magma',vmin=0,interpolation='nearest')
                    panel.fig.colorbar(im,ax=panel.ax,label='Observed span (years)')
                else:
                    im=panel.ax.imshow(a,extent=extent,cmap=ListedColormap(['#d6dbdf','#32a87b']),norm=BoundaryNorm([-.5,.5,1.5],2),interpolation='nearest')
                    panel.fig.colorbar(im,ax=panel.ax,ticks=[0,1],label='Excluded / common valid')
                panel.ax.set_xlabel(crs+' easting (m)'); panel.ax.set_ylabel('Northing (m)')
                panel.toolbar.update(); panel.canvas.draw()
            def save_layer():
                value=layer.currentData(); name=f'pair_valid_{value[0]}_{value[1]}.tif' if isinstance(value,(tuple,list)) else value
                p,_=QFileDialog.getSaveFileName(dialog,'Export full-resolution coverage',str(self.workspace/name),'GeoTIFF (*.tif)')
                if not p: return
                target=Path(p).resolve()
                if target.is_relative_to(folder.resolve()): raise ValueError('Export outside the saved coverage folder to preserve its integrity.')
                if isinstance(value,(tuple,list)):
                    data,grid=pair_mask(folder,*value)
                    write_raster(target,data,grid,'uint8',255,{'stage':doc['stage'],'codes':'0=excluded,1=pair valid,255=outside AOI'})
                else: shutil.copyfile(folder/value,target)
            layer.currentIndexChanged.connect(lambda:self.guard(draw)); export.clicked.connect(lambda:self.guard(save_layer))
            draw(); dialog.exec()
        self.guard(show)
