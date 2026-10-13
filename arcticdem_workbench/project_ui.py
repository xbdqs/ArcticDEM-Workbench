"""Case/project GUI mixin, separate from the catalogue and registration logic."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QDate, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFileDialog, QMessageBox, QInputDialog, QDialog)
from . import __version__
from .common import write_json
from .project import load_project, save_project, absolute_path
from .spatial import normalize_objects, merge_objects


class ProjectMixin:
    def build_project(self):
        self.project_path = None; self.project_id = None; self._saved_signature = None
        self.last_report_dir = None
        self.published_case = None
        self.spatial_objects = {'type':'FeatureCollection','features':[]}
        tab = QWidget(); layout = QVBoxLayout(tab)
        row = QHBoxLayout()
        for label, fn in [('Open project…',self.open_project_dialog),('Save project',self.save_project_dialog),('Save as…',lambda:self.save_project_dialog(True))]:
            row.addWidget(self.button(label, fn))
        self.project_title = QLineEdit(); self.project_title.setPlaceholderText('Case title / 案例名称'); row.addWidget(self.project_title,1)
        layout.addLayout(row)
        self.project_info = QLabel('Project not saved. DEMs/results stay in place; masks are snapshotted at save time.')
        self.project_info.setWordWrap(True); layout.addWidget(self.project_info)
        self.project_notes = QPlainTextEdit(); self.project_notes.setPlaceholderText('Published reference / DOI, process, target dates, stable-terrain rationale, external controls…')
        self.project_notes.setMaximumHeight(95); layout.addWidget(self.project_notes)
        row = QHBoxLayout(); self.object_role = QComboBox()
        for role in ('target','aoi','stable','validation','sample'): self.object_role.addItem(role)
        row.addWidget(QLabel('Default import role')); row.addWidget(self.object_role)
        for label, fn in [('Import GeoJSON…',self.import_objects),('Export all objects…',self.export_objects),('Store current AOI…',self.store_aoi),('Store current point…',self.store_point)]:
            row.addWidget(self.button(label,fn))
        layout.addLayout(row)
        self.object_table = QTableWidget(0,4)
        self.object_table.setHorizontalHeaderLabels(['Name','Role','Geometry','Persistent ID'])
        self.object_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.object_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.object_table.setSelectionMode(QTableWidget.SingleSelection)
        self.object_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.object_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        self.object_table.itemDoubleClicked.connect(lambda item:self.activate_object())
        layout.addWidget(self.object_table,1)
        row = QHBoxLayout()
        for label, fn in [('Use selected object',self.activate_object),('Set role…',self.set_object_role),('Rename…',self.rename_object),('Remove from case',self.remove_object),('Export report + point series…',self.export_case_report)]:
            row.addWidget(self.button(label,fn))
        layout.addLayout(row)
        row=QHBoxLayout()
        self.report_info=QLabel('No case report exported. Reports include shared support, terrain strata, spatial-block diagnostics and comparison conditions.')
        self.report_info.setWordWrap(True);row.addWidget(self.report_info,1)
        for label,fn in [('Open report',self.open_case_report),('Show common support',self.show_common_support),('Export folder',self.open_export_folder)]:
            row.addWidget(self.button(label,fn))
        layout.addLayout(row)
        note = QLabel('Roles: aoi changes the analysis boundary; stable/validation set registration masks; sample loads the fixed point. '
                      'Target polygons define regions for common-support statistics in report export. Import multiple named points to export the same coordinates for every method. '
                      'A project references DEMs/results: move their common parent folder together, not the project JSON alone.')
        note.setWordWrap(True);layout.addWidget(note)
        self.tabs.addTab(tab,'6  Case project')
        menu = self.menuBar().addMenu('Project')
        for label, shortcut, fn in [('Open project…','Ctrl+O',self.open_project_dialog),('Save project','Ctrl+S',self.save_project_dialog),('Save project as…','Ctrl+Shift+S',lambda:self.save_project_dialog(True))]:
            action = QAction(label,self); action.setShortcut(shortcut); action.triggered.connect(fn); menu.addAction(action)

    def case_busy(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self,'Task running','Wait for the current task before replacing or saving a case.');return True
        return False

    def epoch_entries(self):
        entries = json.loads(json.dumps(self.epochs))
        for i, e in enumerate(entries):
            day = self.epochs_table.item(i,0).text().strip(); datetime.strptime(day,'%Y-%m-%d')
            if day != e['date'][:10]: e['date']=day+'T00:00:00Z';e['end_date']=e['date']
        return entries

    def processing_settings(self):
        return {'method':self.method.currentData(),'network':self.network_mode.currentData(),
                'resolution':self.resolution.value(),'block_pixels':self.block_size.value(),'max_shift_m':self.shift_limit.value(),
                'stable_mask':self.stable_path.text().strip() or None,'validation_mask':self.validation_path.text().strip() or None,
                'require_match':self.require_match.isChecked(),'datum_confirmed':self.datum_confirmed.isChecked(),
                'use_query_aoi':self.use_query_aoi.isChecked()}

    def capture_case(self):
        return {'workspace':str(self.workspace),'snapshot':self.snapshot,'checked_ids':[f['id'] for f in self.checked_items()],
                'bbox':self.bbox(),'analysis_geometry':self.aoi_geometry,'epochs':self.epoch_entries(),
                'processing':self.processing_settings(),'processing_bbox':self.processing_bbox,
                'query_controls':{'start':self.date_start.date().toString('yyyy-MM-dd'),'end':self.date_end.date().toString('yyyy-MM-dd'),
                                  'cap':self.cap.value(),'xtrack':self.xtrack.isChecked()},
                'filters':{'text':self.query_filter.text(),'min_aoi':self.min_aoi.value(),'min_valid':self.min_valid.value()},
                'sort':{'column':self.query_table.horizontalHeader().sortIndicatorSection(),
                        'descending':self.query_table.horizontalHeader().sortIndicatorOrder()==Qt.DescendingOrder},
                'objects':self.spatial_objects,'current_point':self.current_point,'published_case':self.published_case,
                'last_report_dir':str(self.last_report_dir) if self.last_report_dir else None,
                'last_coverage_dir':str(self.last_coverage_dir) if self.last_coverage_dir else None,
                'result_dir':str(self.result_dir) if self.result_dir else None,'result_layer':self.layer.currentText()}

    def case_signature(self):
        return json.dumps({'title':self.project_title.text(),'notes':self.project_notes.toPlainText(),
                           'state':self.capture_case()},sort_keys=True,ensure_ascii=False)

    def save_case(self, path):
        doc = save_project(path,self.capture_case(),self.project_title.text(),self.project_notes.toPlainText(),self.project_id)
        self.project_path=Path(path).resolve();self.project_id=doc['project_id']
        for key,widget in [('stable_mask',self.stable_path),('validation_mask',self.validation_path)]:
            frozen=doc['state'].get('processing',{}).get(key)
            if frozen:widget.setText(absolute_path(frozen,self.project_path.parent))
        self._saved_signature=self.case_signature()
        self.project_info.setText(str(self.project_path)+' · saved; keep its .assets folder with this project.')
        self.log(f'Project saved: {self.project_path.name}')
        return True

    def save_project_dialog(self, save_as=False):
        if self.case_busy():return False
        path=self.project_path
        if not path or save_as:
            path,_=QFileDialog.getSaveFileName(self,'Save case project',str(path or self.workspace/'case.arcticdem.json'),'Project (*.arcticdem.json *.json)')
        if not path:return False
        return bool(self.guard(lambda:self.save_case(path)))

    def confirm_case_replace(self):
        try:
            unchanged = self._saved_signature is not None and self.case_signature()==self._saved_signature
        except Exception: unchanged=False
        meaningful = bool(self.snapshot or self.epochs or self.spatial_objects['features'] or self.project_title.text() or self.project_notes.toPlainText())
        if unchanged or not meaningful:return True
        answer=QMessageBox.question(self,'Unsaved case','Save the current case before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Save:return self.save_project_dialog()
        return answer==QMessageBox.Discard

    def restore_case(self, path):
        doc, warnings=load_project(path)  # fully validate before replacing GUI state
        state=doc['state']
        self.cancel_aoi_drawing(False)
        self.snapshot=None;self.common_geometry=None;self.aoi_geometry=None;self.aoi_path=None
        self.current_point=None;self.result_dir=None;self.result_report=None
        self.layer.blockSignals(True);self.layer.clear();self.layer.blockSignals(False)
        for panel in (self.result_panel,self.series_panel,self.network_panel):
            panel.fig.clear();panel.ax=panel.fig.add_subplot(111);panel.canvas.draw_idle()
        self.edge_table.setRowCount(0);self.cycle_table.setRowCount(0);self.result_text.clear()
        self.result_note.setText('No result loaded for this case.');self.network_note.setText('No network loaded for this case.')
        workspace=Path(state.get('workspace') or Path(path).parent/'work')
        if workspace.is_dir():self.workspace=workspace
        else:warnings.append('Saved workspace unavailable; using the currently open workspace.')
        self.workspace_label.setText(str(self.workspace))
        self.query_table.blockSignals(True);self.query_table.setRowCount(0);self.query_table.blockSignals(False)
        if state.get('snapshot'):self.query_loaded(state['snapshot'])
        else:self.query_status.setText('No catalogue snapshot in this project.');self.query_days=0
        for spin,value in zip(self.coords,state.get('bbox',[15.4,78.15,15.6,78.25])):spin.setValue(value)
        self.aoi_geometry=state.get('analysis_geometry');self.aoi_path=None
        checked=set(state.get('checked_ids',[]));self.query_table.blockSignals(True)
        for row in range(self.query_table.rowCount()):
            f=self.feature_for_row(row);self.query_table.item(row,0).setCheckState(Qt.Checked if f['id'] in checked else Qt.Unchecked)
        self.query_table.blockSignals(False)
        sort=state.get('sort',{});self.query_table.sortItems(sort.get('column',1),Qt.DescendingOrder if sort.get('descending') else Qt.AscendingOrder)
        filters=state.get('filters',{});self.query_filter.setText(filters.get('text',''));self.min_aoi.setValue(filters.get('min_aoi',0));self.min_valid.setValue(filters.get('min_valid',0));self.apply_query_filter()
        q=state.get('query_controls',{})
        if q.get('start'):self.date_start.setDate(QDate.fromString(q['start'],'yyyy-MM-dd'))
        if q.get('end'):self.date_end.setDate(QDate.fromString(q['end'],'yyyy-MM-dd'))
        self.cap.setValue(q.get('cap',500));self.xtrack.setChecked(q.get('xtrack',False))
        self.epochs=state.get('epochs',[]);self.refresh_epochs();cfg=state.get('processing',{})
        self.method.setCurrentIndex(self.method.findData(cfg.get('method','none')));self.network_mode.setCurrentIndex(self.network_mode.findData(cfg.get('network','sparse')))
        self.resolution.setValue(cfg.get('resolution',2));self.block_size.setValue(cfg.get('block_pixels',32));self.shift_limit.setValue(cfg.get('max_shift_m',20))
        self.stable_path.setText(cfg.get('stable_mask') or '');self.validation_path.setText(cfg.get('validation_mask') or '')
        self.use_query_aoi.setChecked(cfg.get('use_query_aoi',False));self.require_match.setChecked(cfg.get('require_match',True));self.datum_confirmed.setChecked(cfg.get('datum_confirmed',False))
        self.processing_bbox=state.get('processing_bbox');self.spatial_objects=state['objects'];self.refresh_objects()
        self.published_case=state.get('published_case')
        self.last_report_dir=Path(state['last_report_dir']) if state.get('last_report_dir') else None
        self.refresh_report_info()
        self.last_coverage_dir=Path(state['last_coverage_dir']) if state.get('last_coverage_dir') else None
        self.refresh_coverage_info()
        self.current_point=state.get('current_point')
        result=state.get('result_dir')
        if result and (Path(result)/'report.json').is_file():
            try:
                self.load_results(Path(result))
                if state.get('result_layer') and self.layer.findText(state['result_layer'])>=0:
                    self.layer.setCurrentText(state['result_layer'])
            except Exception as exc:warnings.append(f'Result preview unavailable: {exc}')
        self.project_title.setText(doc.get('title',''));self.project_notes.setPlainText(doc.get('notes',''))
        self.project_path=Path(path).resolve();self.project_id=doc['project_id'];self.draw_map()
        self._saved_signature=self.case_signature()
        self.project_info.setText(str(self.project_path)+(' · missing references: see Logs' if warnings else ' · restored'))
        self.log(f'Project restored: {self.project_path.name}')
        for warning in warnings:self.log(warning)
        return warnings

    def open_project_dialog(self):
        if self.case_busy():return
        path,_=QFileDialog.getOpenFileName(self,'Open case project',str(self.workspace),'Project (*.arcticdem.json *.json)')
        if not path:return
        # Bad input should not trigger loss of the current session.
        if self.guard(lambda:load_project(path)) is None:return
        if not self.confirm_case_replace():return
        warnings=self.guard(lambda:self.restore_case(path))
        if warnings:QMessageBox.warning(self,'Project references','Project opened with warnings. No computation was run.\n\n'+'\n'.join(warnings[:8]))
        self.tabs.setCurrentIndex(5)

    def refresh_objects(self):
        self.object_table.setRowCount(len(self.spatial_objects['features']))
        for row,f in enumerate(self.spatial_objects['features']):
            for col,value in enumerate((f['properties']['name'],f['properties']['role'],f['geometry']['type'],f['id'])):
                self.object_table.setItem(row,col,QTableWidgetItem(str(value)))

    def import_objects(self):
        path,_=QFileDialog.getOpenFileName(self,'Import WGS84 object collection',str(self.workspace),'GeoJSON (*.geojson *.json)')
        if not path:return
        def operation():
            incoming=normalize_objects(json.loads(Path(path).read_text(encoding='utf-8-sig')),self.object_role.currentText())
            self.spatial_objects=merge_objects(self.spatial_objects,incoming);self.refresh_objects()
            self.log(f'Imported {len(incoming["features"])} named spatial objects.')
        self.guard(operation)

    def export_objects(self):
        path,_=QFileDialog.getSaveFileName(self,'Export all named spatial objects',str(self.workspace/'case_objects.geojson'),'GeoJSON (*.geojson)')
        if path:self.guard(lambda:write_json(path,self.spatial_objects))

    def add_named_geometry(self, geometry, role):
        name,ok=QInputDialog.getText(self,'Name spatial object','Persistent name',text=f'{role}_{len(self.spatial_objects["features"])+1}')
        if not ok or not name.strip():return
        incoming=normalize_objects({'type':'Feature','id':str(uuid4()),'properties':{'name':name.strip(),'role':role},'geometry':geometry})
        self.spatial_objects=merge_objects(self.spatial_objects,incoming);self.refresh_objects()

    def store_aoi(self):self.guard(lambda:self.add_named_geometry(self.active_aoi_geometry(),'aoi'))

    def store_point(self):
        if not self.current_point:QMessageBox.information(self,'Sample point','Click a result pixel first.');return
        from pyproj import Transformer
        x,y,crs=self.current_point;lon,lat=Transformer.from_crs(crs,4326,always_xy=True).transform(x,y)
        self.guard(lambda:self.add_named_geometry({'type':'Point','coordinates':[lon,lat]},'sample'))

    def selected_object(self):
        row=self.object_table.currentRow()
        return self.spatial_objects['features'][row] if row>=0 else None

    def activate_object(self):
        f=self.selected_object()
        if not f:return
        def operation():
            role=f['properties']['role']
            if role in ('aoi','target'):
                if role=='target':
                    QMessageBox.information(self,'Target polygon','This boundary is included in region statistics when exporting a case report. To also apply it as the analysis boundary, use a separate object with role aoi.');return
                from shapely.geometry import shape
                from .catalog import validate_bbox
                bbox=list(shape(f['geometry']).bounds);catalog_bbox=validate_bbox(bbox)
                self.aoi_geometry=f['geometry'];self.aoi_path=None;self.common_geometry=None
                for spin,val in zip(self.coords,catalog_bbox):spin.setValue(val)
                self.use_query_aoi.setChecked(True);self.draw_map();self.tabs.setCurrentIndex(0)
            elif role in ('stable','validation'):
                payload={'type':'FeatureCollection','features':[f]}
                digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                path=self.workspace/'spatial_objects'/(digest+'.geojson')
                if not path.exists():write_json(path,payload)
                (self.stable_path if role=='stable' else self.validation_path).setText(str(path));self.tabs.setCurrentIndex(1)
            elif role=='sample':
                if not self.result_dir:QMessageBox.information(self,'Results needed','Open a result before plotting a sample point.');return
                from pyproj import Transformer
                import rasterio
                with rasterio.open(self.result_dir/'epoch_stack.tif') as src:crs=src.crs
                x,y=Transformer.from_crs(4326,crs,always_xy=True).transform(*f['geometry']['coordinates'])
                self.show_timeseries_at(x,y);self.tabs.setCurrentIndex(2)
            self.log(f'Applied object: {f["properties"]["name"]} ({role})')
        self.guard(operation)

    def rename_object(self):
        f=self.selected_object()
        if not f:return
        name,ok=QInputDialog.getText(self,'Rename spatial object','Name (ID remains unchanged)',text=f['properties']['name'])
        if ok and name.strip():f['properties']['name']=name.strip();self.refresh_objects()

    def set_object_role(self):
        f=self.selected_object()
        if not f:return
        choices=['sample'] if f['geometry']['type']=='Point' else ['target','aoi','stable','validation']
        role,ok=QInputDialog.getItem(self,'Set spatial role','Role (ID remains unchanged; click Use to apply)',choices,choices.index(f['properties']['role']),False)
        if ok:f['properties']['role']=role;self.refresh_objects()

    def remove_object(self):
        f=self.selected_object()
        if not f:return
        if QMessageBox.question(self,'Remove object','Remove this reference from the case? External files and active masks are unchanged.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self.spatial_objects['features'].remove(f);self.refresh_objects()

    def export_case_report(self):
        if self.case_busy():return
        if not self.result_dir:QMessageBox.information(self,'Results needed','Open a completed run first.');return
        parent=QFileDialog.getExistingDirectory(self,'Parent folder for new report export',str(self.workspace))
        if not parent:return
        from .reporting import export_report
        dest=Path(parent)/datetime.now().strftime('case_report_%Y%m%d_%H%M%S_%f')
        objects=json.loads(json.dumps(self.spatial_objects));metadata={'title':self.project_title.text(),'notes':self.project_notes.toPlainText(),'project_id':self.project_id,'published_case':self.published_case}
        source=self.result_dir
        self.start('Exporting existing results and fixed points…',lambda log,cancel:export_report(source,dest,objects,metadata,log,cancel),
                   self.case_report_finished)

    def refresh_report_info(self):
        if not self.last_report_dir:
            self.report_info.setText('No report linked to this case.');return
        summary=self.last_report_dir/'common_support'/'summary.json'
        if summary.is_file():
            data=json.loads(summary.read_text(encoding='utf-8'));fraction=data.get('common_fraction')
            ratio=f'{100*fraction:.1f}%' if fraction is not None else 'unavailable'
            audit=data.get('error_structure',{}).get('comparison_contract',{}).get('status','legacy report')
            self.report_info.setText(f"Common support: {data['common_cells']:,} pixels / {ratio} of stored AOI; {len(data['methods'])} method(s). Comparison: {audit}.")
        else:self.report_info.setText('Report: '+str(self.last_report_dir)+' · common-support statistics unavailable.')

    def case_report_finished(self,result):
        self.last_report_dir=Path(result['output']);self.refresh_report_info()
        self.log('Report ready: '+result['html'])
        if result.get('common_support_reason'):self.log('Common support unavailable: '+result['common_support_reason'])

    def open_case_report(self):
        path=self.last_report_dir/'report.html' if self.last_report_dir else None
        if path and path.is_file():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:QMessageBox.information(self,'Report','Export a case report first, or restore a project with an existing report.')

    def open_export_folder(self):
        if self.last_report_dir and self.last_report_dir.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report_dir)))

    def show_common_support(self):
        folder=self.last_report_dir/'common_support' if self.last_report_dir else None
        if not folder or not (folder/'summary.json').is_file():
            QMessageBox.information(self,'Common support','Export a case report with compatible completed results first.');return
        def show():
            from .gui import CanvasPanel
            from .plots import read_preview
            from matplotlib.colors import ListedColormap,BoundaryNorm
            from rasterio.warp import transform_geom
            dialog=QDialog(self);dialog.setWindowTitle('Actual common valid pixels across methods and epochs');dialog.resize(950,780)
            layout=QVBoxLayout(dialog)
            note=QLabel('Green: valid in all included methods and all epochs. Grey: excluded inside the stored AOI. White: outside AOI. Target outlines are orange. The GeoTIFF stores the full-resolution mask.')
            note.setWordWrap(True);layout.addWidget(note);panel=CanvasPanel();layout.addWidget(panel)
            arr,extent,crs=read_preview(folder/'common_valid_mask.tif')
            panel.ax.imshow(arr,extent=extent,origin='upper',interpolation='nearest',cmap=ListedColormap(['#d6dbdf','#32a87b']),norm=BoundaryNorm([-.5,.5,1.5],2))
            objects=json.loads((folder/'target_regions.geojson').read_text(encoding='utf-8'))
            for f in objects['features']:self.plot_geometry(panel.ax,transform_geom(4326,crs,f['geometry']),color='#ae441e',alpha=1)
            panel.ax.set_xlabel(crs+' easting (m)');panel.ax.set_ylabel('Northing (m)');panel.canvas.draw();dialog.exec()
        self.guard(show)
