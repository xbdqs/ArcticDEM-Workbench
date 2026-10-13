from __future__ import annotations
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QDate, QTimer
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
 QTabWidget,QLabel,QLineEdit,QPushButton,QDoubleSpinBox,QSpinBox,QDateEdit,QCheckBox,QComboBox,
 QTableWidget,QTableWidgetItem,QHeaderView,QSplitter,QFileDialog,QMessageBox,QPlainTextEdit,
 QProgressBar,QGroupBox,QFormLayout,QInputDialog,QDialog,QDialogButtonBox)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.widgets import RectangleSelector, PolygonSelector
from matplotlib.collections import LineCollection
from . import __version__
from . import catalog
from .common import write_json
from .raster import download_items, clip_asset
from .pipeline import run,compare_registration_methods
from .plots import read_preview
from .project_ui import ProjectMixin
from .cases_ui import CaseLibraryMixin
from .coverage_ui import CoverageMixin
from .registration_methods import METHOD_LABELS, METHOD_NOTES

FEATURE_ROLE=Qt.UserRole+1
SORT_ROLE=Qt.UserRole+2

class SortItem(QTableWidgetItem):
    def __lt__(self,other):
        left=self.data(SORT_ROLE);right=other.data(SORT_ROLE)
        if left is not None and right is not None:return left<right
        return self.text()<other.text()

class Worker(QThread):
    message=Signal(str)
    succeeded=Signal(object)
    failed=Signal(str)
    def __init__(self,operation):
        super().__init__();self.operation=operation
    def run(self):
        try:self.succeeded.emit(self.operation(self.message.emit,self.isInterruptionRequested))
        except Exception:self.failed.emit(traceback.format_exc())

class CanvasPanel(QWidget):
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.fig=Figure(figsize=(6,4),layout='constrained');self.canvas=FigureCanvasQTAgg(self.fig)
        self.toolbar=NavigationToolbar2QT(self.canvas,self)
        layout.addWidget(self.toolbar);layout.addWidget(self.canvas)
        self.ax=self.fig.add_subplot(111)
        self.interaction_locked=False;self._pan_state=None;self._pan_moved=False;self.last_pan_was_drag=False
        self.canvas.mpl_connect('scroll_event',self._wheel_zoom)
        self.canvas.mpl_connect('button_press_event',self._pan_press)
        self.canvas.mpl_connect('motion_notify_event',self._pan_motion)
        self.canvas.mpl_connect('button_release_event',self._pan_release)

    def _wheel_zoom(self,event):
        """Zoom the primary axes around the cursor; toolbar home restores extent."""
        if event.inaxes is not self.ax or event.xdata is None or event.ydata is None:return
        if self.toolbar.mode:return
        factor=.80 if event.button=='up' else 1.25 if event.button=='down' else None
        if factor is None:return
        self.toolbar.push_current()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim();x,y=event.xdata,event.ydata
        self.ax.set_xlim(x-(x-x0)*factor,x+(x1-x)*factor)
        self.ax.set_ylim(y-(y-y0)*factor,y+(y1-y)*factor)
        self.toolbar.push_current()
        self.canvas.draw_idle()

    def _pan_press(self,event):
        if self.interaction_locked or self.toolbar.mode or event.button!=1 or event.inaxes is not self.ax:return
        if event.xdata is None or event.ydata is None:return
        self.toolbar.push_current()
        self._pan_state=(event.x,event.y,self.ax.get_xlim(),self.ax.get_ylim())
        self._pan_moved=False;self.last_pan_was_drag=False

    def _pan_motion(self,event):
        if self._pan_state is None or event.inaxes is not self.ax or event.xdata is None or event.ydata is None:return
        press_px,press_py,xlim,ylim=self._pan_state
        if not self._pan_moved and np.hypot(event.x-press_px,event.y-press_py)<4:return
        self._pan_moved=True
        dx=(event.x-press_px)/max(self.ax.bbox.width,1)*(xlim[1]-xlim[0])
        dy=(event.y-press_py)/max(self.ax.bbox.height,1)*(ylim[1]-ylim[0])
        self.ax.set_xlim(xlim[0]-dx,xlim[1]-dx);self.ax.set_ylim(ylim[0]-dy,ylim[1]-dy)
        self.canvas.draw_idle()

    def _pan_release(self,event):
        self.last_pan_was_drag=self._pan_moved
        if self._pan_state is not None and self._pan_moved:self.toolbar.push_current()
        self._pan_state=None

class Window(CoverageMixin,CaseLibraryMixin,ProjectMixin,QMainWindow):
    def __init__(self,workspace=None):
        super().__init__();self.setWindowTitle(f'ArcticDEM Workbench {__version__}')
        self.resize(1400,920)
        self.workspace=Path(workspace or Path.cwd()/'work').resolve();self.workspace.mkdir(parents=True,exist_ok=True)
        self.snapshot=None;self.epochs=[];self.worker=None;self.busy_buttons=[];self.result_dir=None
        self.aoi_geometry=None;self.aoi_path=None;self.common_geometry=None;self.current_point=None
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root)
        top=QHBoxLayout();title=QLabel('ArcticDEM Workbench');title.setObjectName('title')
        top.addWidget(title);top.addStretch();self.workspace_label=QLabel(str(self.workspace));top.addWidget(self.workspace_label)
        b=QPushButton('Workspace…');b.clicked.connect(self.choose_workspace);self.busy_buttons.append(b);top.addWidget(b);layout.addLayout(top)
        subtitle=QLabel('Find observations · inspect temporal support · measure elevation change');subtitle.setObjectName('subtitle');layout.addWidget(subtitle)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.build_search();self.build_processing();self.build_results();self.build_network();self.build_log();self.build_project();self.build_case_library()
        status=QHBoxLayout();self.status=QLabel('Ready');status.addWidget(self.status,1)
        self.progress=QProgressBar();self.progress.setMaximumWidth(220);self.progress.setRange(0,1);self.progress.setValue(0);status.addWidget(self.progress)
        self.cancel=QPushButton('Cancel task');self.cancel.setEnabled(False);self.cancel.clicked.connect(self.cancel_task);status.addWidget(self.cancel);layout.addLayout(status)
        self.setStyleSheet('QMainWindow {background:#f2f5f7;} QWidget {font-size:12px;} QLabel#title {font-size:24px;font-weight:650;color:#143847;} QLabel#subtitle {color:#536873;} QGroupBox {font-weight:bold;margin-top:12px;padding-top:12px;} QPushButton {padding:7px 12px;} QLineEdit,QSpinBox,QDoubleSpinBox,QDateEdit,QComboBox {padding:5px;} QTabBar::tab {padding:10px 18px;} QTableWidget {background:white;}')
        self.draw_map(True);self.log('Workspace ready. First run: use the synthetic demo, then query a small real AOI.')

    def button(self,text,callback):
        b=QPushButton(text);b.clicked.connect(callback);self.busy_buttons.append(b);return b

    def choose_workspace(self):
        p=QFileDialog.getExistingDirectory(self,'Workspace',str(self.workspace))
        if p:self.workspace=Path(p);self.workspace_label.setText(p)

    def log(self,message):
        line=f'{datetime.now():%H:%M:%S}  {message}'
        self.log_text.appendPlainText(line)
        with (self.workspace/'workbench.log').open('a',encoding='utf-8') as f:f.write(line+'\n')
        self.status.setText(message[:160])

    def start(self,name,operation,success):
        if self.worker and self.worker.isRunning():return
        for b in self.busy_buttons:b.setEnabled(False)
        self.cancel.setEnabled(True);self.progress.setRange(0,0);self.log(name)
        self.worker=Worker(operation);self.worker.message.connect(self.log)
        self.worker.succeeded.connect(success);self.worker.failed.connect(self.task_error);self.worker.finished.connect(self.task_finished);self.worker.start()

    def task_finished(self):
        for b in self.busy_buttons:b.setEnabled(True)
        self.cancel.setEnabled(False);self.progress.setRange(0,1);self.progress.setValue(1)

    def task_error(self,error):
        self.log(error);QMessageBox.warning(self,'Task stopped',error.splitlines()[-1]+'\n\nFull details are available in Logs.')

    def cancel_task(self):
        if self.worker:self.worker.requestInterruption();self.log('Cancellation requested; waiting for the current bounded operation to return.')

    def guard(self,operation):
        try:return operation()
        except Exception as exc:QMessageBox.warning(self,'Check inputs',str(exc));return None

    def build_search(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        box=QGroupBox('Area and acquisition dates');form=QGridLayout(box)
        self.coords=[]
        for c,(label,val) in enumerate(zip(['West','South','East','North'],[15.40,78.15,15.60,78.25])):
            s=QDoubleSpinBox();s.setRange(-180,180);s.setDecimals(5);s.setValue(val);s.setSingleStep(.01)
            form.addWidget(QLabel(label),0,c*2);form.addWidget(s,0,c*2+1);self.coords.append(s)
            s.editingFinished.connect(self.coordinates_edited)
        self.date_start=QDateEdit(QDate(2007,1,1));self.date_end=QDateEdit(QDate.currentDate())
        for d in (self.date_start,self.date_end):d.setCalendarPopup(True);d.setDisplayFormat('yyyy-MM-dd')
        self.cap=QSpinBox();self.cap.setRange(1,10000);self.cap.setValue(500)
        self.xtrack=QCheckBox('Include cross-track stereo pairs');self.xtrack.setToolTip('These pairs can use images from different days. Inspect both acquisition times.')
        for c,w in enumerate([QLabel('From'),self.date_start,QLabel('To'),self.date_end,QLabel('Record cap'),self.cap,self.xtrack]):form.addWidget(w,1,c)
        layout.addWidget(box)
        buttons=QHBoxLayout()
        for label,fn in [('Search catalogue',self.do_search),('Load query…',self.load_query),('Save query…',self.save_query),('Show AOI',self.draw_map),('Fit footprints',self.fit_footprints),('Draw AOI',self.enable_rectangle),('Arctic extent',lambda:self.draw_map(True))]:buttons.addWidget(self.button(label,fn))
        buttons.addStretch();layout.addLayout(buttons)
        spatial=QHBoxLayout()
        for label,fn in [('Import AOI…',self.import_aoi),('Export AOI…',self.export_aoi),('Show checked common footprint',self.show_common_footprint),('Export common footprint…',self.export_common_footprint)]:spatial.addWidget(self.button(label,fn))
        spatial.addStretch();layout.addLayout(spatial)
        self.query_status=QLabel('Enter a small AOI or draw one on the map. Footprints indicate candidate coverage.');self.query_status.setWordWrap(True);layout.addWidget(self.query_status)
        split=QSplitter(Qt.Horizontal);self.map_panel=CanvasPanel();split.addWidget(self.map_panel)
        right=QWidget();r=QVBoxLayout(right);r.setContentsMargins(0,0,0,0)
        self.query_table=QTableWidget(0,7);self.query_table.setHorizontalHeaderLabels(['Use','Start','End','AOI footprint','Strip valid','Sensor','Strip ID'])
        self.query_table.setSelectionBehavior(QTableWidget.SelectRows);self.query_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.query_table.setSortingEnabled(True);self.query_table.setAlternatingRowColors(True)
        self.query_table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch)
        filters=QHBoxLayout();self.query_filter=QLineEdit();self.query_filter.setPlaceholderText('Filter sensor, date or Strip ID…')
        self.min_aoi=QDoubleSpinBox();self.min_aoi.setRange(0,100);self.min_aoi.setSuffix('% AOI min');self.min_aoi.setDecimals(1)
        self.min_valid=QDoubleSpinBox();self.min_valid.setRange(0,100);self.min_valid.setSuffix('% strip valid min');self.min_valid.setDecimals(1)
        for widget in (self.query_filter,self.min_aoi,self.min_valid):filters.addWidget(widget)
        filters.addWidget(self.button('Reset filter',self.reset_query_filter));r.addLayout(filters)
        self.query_filter.textChanged.connect(self.apply_query_filter);self.min_aoi.valueChanged.connect(self.apply_query_filter);self.min_valid.valueChanged.connect(self.apply_query_filter)
        self.query_table.itemSelectionChanged.connect(self.highlight_selection);self.query_table.itemChanged.connect(self.update_check_summary);r.addWidget(self.query_table)
        row=QGridLayout()
        for i,(label,fn) in enumerate([('Check rows',self.check_selected),('Check visible',self.check_visible),('Check all',self.check_all),('Uncheck all',self.clear_checks),('Invert visible',self.invert_checks),('Suggest ≤12 dates',self.suggest_dates),('Preview',self.preview_selected),('Download checked',self.download_checked)]):row.addWidget(self.button(label,fn),i//4,i%4)
        r.addLayout(row);self.epoch_summary=QLabel('No query loaded.');self.epoch_summary.setWordWrap(True);r.addWidget(self.epoch_summary)
        split.addWidget(right);split.setSizes([520,780]);layout.addWidget(split,1)
        self.tabs.addTab(tab,'1  Search / browse')

    def bbox(self):return catalog.validate_bbox([s.value() for s in self.coords])

    def bbox_geometry(self):
        w,s,e,n=self.bbox();return {'type':'Polygon','coordinates':[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}

    def active_aoi_geometry(self):return self.aoi_geometry or self.bbox_geometry()

    def coordinates_edited(self):
        values=tuple(s.value() for s in self.coords)
        if values==getattr(self,'_display_bbox',None):return
        # Focus changes alone must not discard an imported polygon. A changed
        # coordinate, however, explicitly replaces it with the displayed box.
        self.aoi_geometry=None;self.aoi_path=None;self.common_geometry=None
        self.cancel_aoi_drawing(False);self.draw_map()
        if self.snapshot:
            self.query_status.setText('AOI coordinates changed. Search again to refresh catalogue coverage values; current rows belong to the previous query.')


    def import_aoi(self):
        p,_=QFileDialog.getOpenFileName(self,'Import WGS84 analysis AOI',str(self.workspace),'GeoJSON (*.geojson *.json)')
        if not p:return
        def load():
            from shapely.geometry import shape,mapping
            obj=json.loads(Path(p).read_text(encoding='utf-8-sig'))
            if obj.get('crs'):raise ValueError('AOI GeoJSON must use WGS84 longitude/latitude and omit the legacy CRS member.')
            geoms=[f['geometry'] for f in obj['features']] if obj.get('type')=='FeatureCollection' else [obj['geometry']] if obj.get('type')=='Feature' else [obj]
            merged=None
            from shapely.ops import unary_union
            merged=unary_union([shape(g) for g in geoms])
            if merged.is_empty or merged.geom_type not in ('Polygon','MultiPolygon'):raise ValueError('AOI requires Polygon or MultiPolygon geometry.')
            w,s,e,n=merged.bounds;catalog.validate_bbox([w,s,e,n])
            self.aoi_geometry=mapping(merged);self.aoi_path=str(Path(p).resolve());self.common_geometry=None
            for spin,value in zip(self.coords,[w,s,e,n]):spin.setValue(value)
            self.draw_map();self.log(f'AOI imported: {Path(p).name}')
        self.guard(load)

    def export_aoi(self):
        p,_=QFileDialog.getSaveFileName(self,'Export analysis AOI',str(self.workspace/'analysis_aoi.geojson'),'GeoJSON (*.geojson)')
        if p:
            write_json(p,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'role':'analysis AOI'},'geometry':self.active_aoi_geometry()}]})
            self.aoi_path=str(Path(p).resolve());self.log(f'AOI exported: {Path(p).name}')

    def show_common_footprint(self):
        items=self.checked_items()
        if not items:QMessageBox.information(self,'Common footprint','Check at least one catalogue strip first.');return
        def calculate():
            from shapely.geometry import shape,mapping
            common=shape(self.active_aoi_geometry())
            for item in items:common=common.intersection(shape(item['geometry']))
            self.common_geometry=mapping(common) if not common.is_empty else None
            self.draw_map()
            fraction=100*common.area/max(shape(self.active_aoi_geometry()).area,1e-30)
            self.query_status.setText(f'Checked-strip geometric common footprint: {fraction:.1f}% of the AOI. Actual quality-valid common pixels are calculated after download.')
        self.guard(calculate)

    def export_common_footprint(self):
        if not self.common_geometry:QMessageBox.information(self,'Common footprint','Calculate a non-empty checked-strip common footprint first.');return
        p,_=QFileDialog.getSaveFileName(self,'Export geometric common footprint',str(self.workspace/'common_footprint.geojson'),'GeoJSON (*.geojson)')
        if p:write_json(p,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'role':'checked-strip geometric common footprint'},'geometry':self.common_geometry}]});self.log(f'Common footprint exported: {Path(p).name}')

    def do_search(self):
        bbox=self.guard(self.bbox)
        if not bbox:return
        start=self.date_start.date().toString('yyyy-MM-dd');end=self.date_end.date().toString('yyyy-MM-dd');cap=self.cap.value();xt=self.xtrack.isChecked()
        self.start('Querying PGC ArcticDEM…',lambda log,cancel:catalog.search(bbox,start,end,cap,xt,log,cancel),self.query_loaded)

    def query_loaded(self,snapshot):
        self.snapshot=snapshot
        meta=snapshot.get('workbench',{})
        if meta.get('start'):self.date_start.setDate(QDate.fromString(meta['start'][:10],'yyyy-MM-dd'))
        if meta.get('end'):self.date_end.setDate(QDate.fromString(meta['end'][:10],'yyyy-MM-dd'))
        if meta.get('query_cap'):self.cap.setValue(meta['query_cap'])
        self.xtrack.setChecked(bool(meta.get('include_xtrack',False)))
        bbox=snapshot.get('workbench',{}).get('bbox')
        if bbox:
            if tuple(bbox)!=tuple(s.value() for s in self.coords):
                self.aoi_geometry=None;self.aoi_path=None
            for s,v in zip(self.coords,bbox):s.setValue(v)
        self.common_geometry=None
        rows=catalog.item_rows(snapshot);self.query_table.setSortingEnabled(False);self.query_table.blockSignals(True);self.query_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            check=SortItem();check.setFlags(Qt.ItemIsUserCheckable|Qt.ItemIsEnabled|Qt.ItemIsSelectable);check.setCheckState(Qt.Unchecked);check.setData(FEATURE_ROLE,i);self.query_table.setItem(i,0,check)
            frac=row['footprint_aoi_fraction'];sf=row['source_valid_fraction']
            sf_pct=(float(sf)*100 if 0<=float(sf)<=1 else float(sf)) if sf!='' and 0<=float(sf)<=100 else None
            vals=[row['start'][:10],row['end'][:10],f'{float(frac)*100:.1f}%' if frac!='' else '',f'{sf_pct:.1f}%' if sf_pct is not None else '',row['sensor'],row['id']]
            for c,value in enumerate(vals,1):
                item=SortItem(str(value));item.setToolTip(str(value));item.setData(FEATURE_ROLE,i)
                if c==3:item.setData(SORT_ROLE,float(frac)*100 if frac!='' else -1.)
                if c==4:item.setData(SORT_ROLE,sf_pct if sf_pct is not None else -1.)
                self.query_table.setItem(i,c,item)
        self.query_table.blockSignals(False);self.query_table.setSortingEnabled(True);self.query_table.resizeColumnsToContents();self.query_table.setColumnWidth(6,260);self.apply_query_filter()
        meta=snapshot.get('workbench',{});truncated=meta.get('truncated',False)
        self.query_status.setText(f"{len(rows)} strips retained. Query {'STOPPED AT CAP — coverage is incomplete' if truncated else 'completed for requested filters'}. AOI footprint is geometric coverage; strip valid fraction is a whole-strip source metric.")
        days=len({catalog.item_times(f)[0][:10] for f in snapshot['features']})
        self.query_days=days;self.update_check_summary()
        catalog.save_snapshot(snapshot,self.workspace/'latest_query.geojson');self.draw_map();self.log('Query snapshot and CSV saved.')

    def load_query(self):
        p,_=QFileDialog.getOpenFileName(self,'Load STAC query',str(self.workspace),'JSON (*.json *.geojson)')
        if p:self.guard(lambda:self.query_loaded(json.loads(Path(p).read_text(encoding='utf-8-sig'))))

    def save_query(self):
        if not self.snapshot:return
        p,_=QFileDialog.getSaveFileName(self,'Save query',str(self.workspace/'query.geojson'),'GeoJSON (*.geojson)')
        if p:self.guard(lambda:catalog.save_snapshot(self.snapshot,p))

    def draw_map(self,arctic=False):
        try:b=self.bbox()
        except ValueError:return
        self._display_bbox=tuple(b)
        ax=self.map_panel.ax;ax.clear()
        coast=Path(__file__).parent/'assets'/'ne_110m_coastline.geojson'
        if coast.exists():
            obj=json.loads(coast.read_text(encoding='utf-8'))
            lines=[]
            for f in obj['features']:
                geom=f['geometry'];coords=geom['coordinates']
                lines.extend([coords] if geom['type']=='LineString' else coords)
            ax.add_collection(LineCollection(lines,colors='#6f858d',linewidths=.7))
        if self.snapshot:
            for f in self.snapshot['features']:
                self.plot_geometry(ax,f.get('geometry'),color='#2395a2',alpha=.22)
        self.plot_geometry(ax,self.active_aoi_geometry(),color='#d27a38',alpha=1)
        if self.common_geometry:self.plot_geometry(ax,self.common_geometry,color='#2b8c4b',alpha=1)
        if arctic is True:ax.set_xlim(-180,180);ax.set_ylim(45,89)
        else:
            dx=max((b[2]-b[0])*.2,.015);dy=max((b[3]-b[1])*.2,.01)
            ax.set_xlim(b[0]-dx,b[2]+dx);ax.set_ylim(b[1]-dy,b[3]+dy)
        ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.grid(alpha=.15);ax.set_facecolor('#e9f1f4')
        ax.set_aspect(1/max(np.cos(np.deg2rad((b[1]+b[3])/2)),.12) if arctic is not True else 'auto')
        self.map_panel.canvas.draw_idle()

    def plot_geometry(self,ax,geom,**kwargs):
        if not geom:return
        polys=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates'] if geom['type']=='MultiPolygon' else []
        for poly in polys:
            arr=np.asarray(poly[0]);ax.plot(arr[:,0],arr[:,1],linewidth=.8,**kwargs)

    def enable_rectangle(self):
        self.cancel_aoi_drawing(False)
        self.map_panel.interaction_locked=True
        self.rectangle=RectangleSelector(self.map_panel.ax,self.aoi_selected,useblit=True,button=[1],interactive=False)
        self.rectangle_key=self.map_panel.canvas.mpl_connect('key_press_event',self.aoi_key)
        self.log('AOI drawing active: drag a rectangle. Normal left-drag map panning resumes after the rectangle is completed.')

    def aoi_key(self,event):
        if event.key=='escape':self.cancel_aoi_drawing()

    def cancel_aoi_drawing(self,notify=True):
        selector=getattr(self,'rectangle',None)
        if selector:selector.set_active(False);selector.disconnect_events();self.rectangle=None
        key=getattr(self,'rectangle_key',None)
        if key:self.map_panel.canvas.mpl_disconnect(key);self.rectangle_key=None
        if hasattr(self,'map_panel'):self.map_panel.interaction_locked=False
        if notify:self.log('AOI drawing cancelled; map panning restored.')

    def fit_footprints(self):
        if not self.snapshot or not self.snapshot['features']:return
        extents=[f['bbox'] for f in self.snapshot['features'] if f.get('bbox') and len(f['bbox'])==4]
        if not extents:return
        self.draw_map();w=min(b[0] for b in extents);s=min(b[1] for b in extents);e=max(b[2] for b in extents);n=max(b[3] for b in extents)
        dx=max((e-w)*.05,.005);dy=max((n-s)*.05,.005)
        self.map_panel.ax.set_xlim(w-dx,e+dx);self.map_panel.ax.set_ylim(s-dy,n+dy);self.map_panel.canvas.draw_idle()

    def aoi_selected(self,left,right):
        if None in (left.xdata,left.ydata,right.xdata,right.ydata):return
        bbox=[min(left.xdata,right.xdata),min(left.ydata,right.ydata),max(left.xdata,right.xdata),max(left.ydata,right.ydata)]
        if self.guard(lambda:catalog.validate_bbox(bbox)):
            for s,v in zip(self.coords,bbox):s.setValue(v)
            self.aoi_geometry=self.bbox_geometry();self.aoi_path=None;self.common_geometry=None
        self.cancel_aoi_drawing(False);self.draw_map()

    def highlight_selection(self):
        if not self.snapshot:return
        row=self.query_table.currentRow()
        if row<0:return
        feature=self.feature_for_row(row)
        if not feature:return
        self.draw_map();self.plot_geometry(self.map_panel.ax,feature.get('geometry'),color='#c84c32',alpha=1)
        self.map_panel.canvas.draw_idle()

    def feature_for_row(self,row):
        if not self.snapshot or row<0:return None
        item=self.query_table.item(row,0);index=item.data(FEATURE_ROLE) if item else None
        return self.snapshot['features'][int(index)] if index is not None else None

    def visible_rows(self):return [i for i in range(self.query_table.rowCount()) if not self.query_table.isRowHidden(i)]

    def apply_query_filter(self,*args):
        text=self.query_filter.text().strip().casefold();min_aoi=self.min_aoi.value();min_valid=self.min_valid.value()
        for row in range(self.query_table.rowCount()):
            hay=' '.join(self.query_table.item(row,c).text() for c in (1,2,5,6)).casefold()
            aoi=self.query_table.item(row,3).data(SORT_ROLE);valid=self.query_table.item(row,4).data(SORT_ROLE)
            show=(not text or text in hay) and (min_aoi==0 or aoi>=min_aoi) and (min_valid==0 or valid>=min_valid)
            self.query_table.setRowHidden(row,not show)
        self.update_check_summary()

    def reset_query_filter(self):
        self.query_filter.clear();self.min_aoi.setValue(0);self.min_valid.setValue(0);self.apply_query_filter()

    def check_selected(self):
        self.query_table.blockSignals(True)
        for row in {x.row() for x in self.query_table.selectedIndexes()}:self.query_table.item(row,0).setCheckState(Qt.Checked)
        self.query_table.blockSignals(False);self.checks_changed()

    def check_all(self):
        self.query_table.blockSignals(True)
        for i in range(self.query_table.rowCount()):self.query_table.item(i,0).setCheckState(Qt.Checked)
        self.query_table.blockSignals(False);self.checks_changed()

    def check_visible(self):
        self.query_table.blockSignals(True)
        for i in self.visible_rows():self.query_table.item(i,0).setCheckState(Qt.Checked)
        self.query_table.blockSignals(False);self.checks_changed()

    def invert_checks(self):
        self.query_table.blockSignals(True)
        for i in self.visible_rows():
            item=self.query_table.item(i,0);item.setCheckState(Qt.Unchecked if item.checkState()==Qt.Checked else Qt.Checked)
        self.query_table.blockSignals(False);self.checks_changed()

    def suggest_dates(self):
        candidates={}
        for row in self.visible_rows():
            day=self.query_table.item(row,1).text();aoi=self.query_table.item(row,3).data(SORT_ROLE);valid=self.query_table.item(row,4).data(SORT_ROLE)
            score=(aoi,valid)
            if day not in candidates or score>candidates[day][0]:candidates[day]=(score,row)
        days=sorted(candidates)
        if len(days)>12:
            indices=sorted(set(np.rint(np.linspace(0,len(days)-1,12)).astype(int)));days=[days[i] for i in indices]
        self.query_table.blockSignals(True)
        for i in range(self.query_table.rowCount()):self.query_table.item(i,0).setCheckState(Qt.Unchecked)
        for day in days:self.query_table.item(candidates[day][1],0).setCheckState(Qt.Checked)
        self.query_table.blockSignals(False);self.checks_changed();self.log(f'Suggested {len(days)} temporally distributed dates; review source-image dependencies before download.')

    def clear_checks(self):
        self.query_table.blockSignals(True)
        for i in range(self.query_table.rowCount()):self.query_table.item(i,0).setCheckState(Qt.Unchecked)
        self.query_table.blockSignals(False);self.checks_changed()

    def checks_changed(self):
        self.common_geometry=None;self.update_check_summary();self.draw_map()

    def update_check_summary(self,item=None):
        if item is not None and item.column()!=0:return
        if item is not None:
            self.common_geometry=None;self.draw_map()
        selected=self.checked_items();checked=len(selected);total=self.query_table.rowCount();visible=len(self.visible_rows());days=getattr(self,'query_days',0)
        selected_days=len({catalog.item_times(f)[0][:10] for f in selected});conflicts=len(catalog.dependency_warnings(selected)) if checked<=100 else 0
        extra=' Download batches are limited to 12 strips.' if checked>12 else ''
        conflict_text=f' {conflicts} same-day/shared-image conflict(s).' if conflicts else ''
        self.epoch_summary.setText(f'{checked}/{total} checked ({selected_days} dates); {visible} visible; {days} dates returned.{conflict_text}{extra}')

    def checked_items(self):
        if not self.snapshot:return []
        return [self.feature_for_row(i) for i in range(self.query_table.rowCount()) if self.query_table.item(i,0).checkState()==Qt.Checked]

    def preview_selected(self):
        if not self.snapshot or self.query_table.currentRow()<0:return
        f=self.feature_for_row(self.query_table.currentRow());bbox=self.guard(self.bbox)
        if not bbox:return
        url=f['assets'].get('hillshade_masked',f['assets'].get('hillshade',f['assets']['dem']))['href']
        output=self.workspace/'previews'/f"{f['id']}.tif"
        self.start('Reading strip preview…',lambda log,cancel:clip_asset(url,bbox,output,log,cancel),lambda p:self.show_preview(p,f['id']))

    def show_preview(self,path,title):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(850,700);layout=QVBoxLayout(dialog);panel=CanvasPanel();layout.addWidget(panel)
        arr,extent,crs=read_preview(path);panel.ax.imshow(arr,extent=extent,cmap='gray',origin='upper');panel.ax.set_xlabel(crs+' easting');panel.ax.set_ylabel('Northing');panel.canvas.draw()
        dialog.exec()

    def download_checked(self):
        items=self.checked_items();bbox=self.guard(self.bbox)
        if not items or not bbox:return
        if len(items)>12:QMessageBox.information(self,'Selection','Choose no more than 12 strips per first-release batch.');return
        warnings=catalog.dependency_warnings(items)
        if warnings:self.log('\n'.join(warnings))
        self.start('Downloading native AOI clips and quality masks…',lambda log,cancel:download_items(items,bbox,self.workspace/'clips',log,cancel),self.download_finished)

    def download_finished(self,result):
        if any(e['id'].startswith('SYNTHETIC_') for e in self.epochs):
            self.epochs=[];self.stable_path.clear();self.validation_path.clear();self.method.setCurrentIndex(0)
        known={e['id'] for e in self.epochs}
        self.epochs.extend([e for e in result['epochs'] if e['id'] not in known]);self.processing_bbox=result['bbox'];self.use_query_aoi.setChecked(True)
        self.refresh_epochs();self.tabs.setCurrentIndex(1);self.log(f"{len(result['epochs'])} complete clips ready; {len(result['failures'])} failed.")

    def build_processing(self):
        tab=QWidget();layout=QVBoxLayout(tab);row=QHBoxLayout()
        for label,fn in [('Import downloaded epochs…',self.import_epochs),('Add local DEMs…',self.add_local),('Remove selected',self.remove_epochs),('Load synthetic demo',self.load_demo)]:row.addWidget(self.button(label,fn))
        row.addStretch();layout.addLayout(row)
        self.epochs_table=QTableWidget(0,4);self.epochs_table.setHorizontalHeaderLabels(['Acquisition date','Epoch ID','Quality masks','DEM path'])
        self.epochs_table.setSelectionBehavior(QTableWidget.SelectRows);self.epochs_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);layout.addWidget(self.epochs_table,1)
        controls=QGroupBox('DoD and temporal network');form=QGridLayout(controls)
        self.method=QComboBox()
        for method in ('none','vertical','translation','nuth_kaab','joint_gradient','compare'):
            self.method.addItem(METHOD_LABELS[method],method)
        self.network_mode=QComboBox();self.network_mode.addItem('Sparse redundant network','sparse');self.network_mode.addItem('All pairs (max. 12 epochs)','all');self.network_mode.addItem('Adjacent chain (no closure test)','chain')
        self.resolution=QDoubleSpinBox();self.resolution.setRange(2,100);self.resolution.setValue(2);self.resolution.setSuffix(' m')
        self.block_size=QSpinBox();self.block_size.setRange(8,2048);self.block_size.setValue(32);self.block_size.setSuffix(' px')
        self.shift_limit=QDoubleSpinBox();self.shift_limit.setRange(.1,100);self.shift_limit.setValue(20);self.shift_limit.setSuffix(' m')
        for row,(a,b,c,d) in enumerate([('Registration',self.method,'Pair network',self.network_mode),('Grid resolution',self.resolution,'Validation block',self.block_size),('Max horizontal sampling shift',self.shift_limit,'',QLabel('2 epochs: pair DoD  |  3–12 epochs: stack + temporal outputs'))]):
            form.addWidget(QLabel(a),row,0);form.addWidget(b,row,1);form.addWidget(QLabel(c),row,2);form.addWidget(d,row,3)
        self.stable_path=QLineEdit();self.validation_path=QLineEdit()
        for row,label,field in [(3,'Stable terrain mask',self.stable_path),(4,'Separate validation mask',self.validation_path)]:
            form.addWidget(QLabel(label),row,0);form.addWidget(field,row,1,1,2)
            form.addWidget(self.button('Browse…',lambda checked=False,f=field:self.pick_mask(f)),row,3)
        form.addWidget(self.button('Draw stable polygon on first DEM…',self.draw_stable),5,1)
        self.use_query_aoi=QCheckBox('Use current query AOI');self.processing_bbox=None;form.addWidget(self.use_query_aoi,5,2)
        self.require_match=QCheckBox('Keep matched pixels when matchtag is supplied');self.require_match.setChecked(True);form.addWidget(self.require_match,6,0,1,2)
        self.datum_confirmed=QCheckBox('Local inputs share a vertical datum and use metres');form.addWidget(self.datum_confirmed,6,2,1,2)
        layout.addWidget(controls)
        self.method_note=QLabel();self.method_note.setWordWrap(True);layout.addWidget(self.method_note)
        self.method.currentIndexChanged.connect(self.update_method_note);self.update_method_note()
        self.build_coverage_controls(layout)
        row=QHBoxLayout();row.addWidget(self.button('Run DoD / multi-epoch analysis',self.process));row.addWidget(self.button('Save job configuration…',self.save_job));row.addStretch();layout.addLayout(row)
        self.tabs.addTab(tab,'2  Epochs / DoD')

    def update_method_note(self):
        self.method_note.setText(METHOD_NOTES[self.method.currentData()]+
            ' Network closure checks relative consistency; it cannot establish absolute accuracy.')

    def refresh_epochs(self):
        self.epochs.sort(key=lambda e:e['date']);self.epochs_table.setRowCount(len(self.epochs))
        for r,e in enumerate(self.epochs):
            vals=[e['date'][:10],e['id'],'bitmask + matchtag' if e.get('mask') and e.get('matchtag') else 'incomplete / not supplied',e['dem']]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v)
                if c or e.get('image_ids'):item.setFlags(item.flags()&~Qt.ItemIsEditable)
                item.setToolTip(v);self.epochs_table.setItem(r,c,item)
        self.epochs_table.resizeColumnsToContents();self.epochs_table.setColumnWidth(1,340)

    def import_epochs(self):
        p,_=QFileDialog.getOpenFileName(self,'Epoch manifest',str(self.workspace),'JSON (*.json)')
        if not p:return
        def load():
            obj=json.loads(Path(p).read_text(encoding='utf-8-sig'))
            for e in obj['epochs']:
                for key in ('dem','mask','matchtag','source_item'):
                    if e.get(key) and not Path(e[key]).is_absolute():e[key]=str((Path(p).parent/e[key]).resolve())
            self.epochs=obj['epochs'];self.processing_bbox=obj.get('bbox')
            if self.processing_bbox:
                for spin,value in zip(self.coords,self.processing_bbox):spin.setValue(value)
                self.use_query_aoi.setChecked(True)
            self.refresh_epochs()
        self.guard(load)

    def add_local(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Local DEM GeoTIFFs',str(self.workspace),'GeoTIFF (*.tif *.tiff)')
        for p in paths:
            match=re.search(r'((?:19|20)\d{2})(?:[-_]?)(\d{2})(?:[-_]?)(\d{2})',Path(p).name)
            default='-'.join(match.groups()) if match else '2010-08-01'
            value,ok=QInputDialog.getText(self,'Acquisition date',Path(p).name+' — YYYY-MM-DD',text=default)
            if not ok:continue
            if self.guard(lambda:datetime.strptime(value,'%Y-%m-%d')) is None:continue
            e={'id':Path(p).stem,'date':value+'T00:00:00Z','dem':p,'units':'m','vertical_datum':'unknown','image_ids':[]}
            for key,name in [('mask','bitmask.tif'),('matchtag','matchtag.tif')]:
                candidate=Path(p).with_name(name)
                original=Path(str(p).replace('_dem.tif','_'+name))
                if candidate.exists() and candidate!=Path(p):e[key]=str(candidate)
                elif original.exists() and original!=Path(p):e[key]=str(original)
            self.epochs.append(e)
        self.refresh_epochs()

    def remove_epochs(self):
        rows={i.row() for i in self.epochs_table.selectedIndexes()};self.epochs=[e for i,e in enumerate(self.epochs) if i not in rows];self.refresh_epochs()

    def load_demo(self):
        from .demo import create_demo
        cfg=create_demo(self.workspace/'synthetic_demo')
        self.epochs=cfg['epochs'];self.stable_path.setText(cfg['stable_mask']);self.validation_path.clear();self.method.setCurrentIndex(1);self.network_mode.setCurrentIndex(1)
        self.datum_confirmed.setChecked(True);self.use_query_aoi.setChecked(False);self.refresh_epochs();self.log('Synthetic demo loaded: known offsets and central lowering. These are not satellite observations.')

    def pick_mask(self,field):
        p,_=QFileDialog.getOpenFileName(self,'Stable/validation terrain (positive raster values or WGS84 polygons)',str(self.workspace),'Masks (*.tif *.tiff *.geojson *.json)')
        if p:field.setText(p)

    def draw_stable(self):
        if not self.epochs:QMessageBox.information(self,'DEM needed','Add or download a DEM first.');return
        dialog=QDialog(self);dialog.setWindowTitle('Draw one stable-terrain polygon');dialog.resize(950,750);layout=QVBoxLayout(dialog)
        note=QLabel('Click vertices, then click the first vertex to finish. Select known stable terrain from independent knowledge; DEM appearance alone cannot establish stability. Existing glaciers, snow, vegetation and changing slopes should be excluded.');note.setWordWrap(True);layout.addWidget(note)
        panel=CanvasPanel();panel.interaction_locked=True;layout.addWidget(panel);arr,extent,crs=read_preview(self.epochs[0]['dem']);panel.ax.imshow(arr,extent=extent,cmap='terrain');panel.ax.set_xlabel(crs+' easting');panel.ax.set_ylabel('Northing')
        vertices=[]
        def selected(v):vertices[:]=v
        selector=PolygonSelector(panel.ax,selected,useblit=True);panel.canvas.draw()
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted and len(vertices)>=3:
            from pyproj import Transformer
            transform=Transformer.from_crs(crs,4326,always_xy=True)
            ring=[list(transform.transform(x,y)) for x,y in vertices];ring.append(ring[0])
            path=self.workspace/f'stable_polygon_{datetime.now():%Y%m%d_%H%M%S}.geojson'
            write_json(path,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'role':'user-defined stable terrain'},'geometry':{'type':'Polygon','coordinates':[ring]}}]})
            self.stable_path.setText(str(path));self.log(f'Stable polygon saved: {path.name}')
        selector.disconnect_events()

    def job(self):
        if len(self.epochs)<2:raise ValueError('Add at least two epochs.')
        entries=self.epoch_entries()
        out=self.workspace/'results'/datetime.now().strftime('run_%Y%m%d_%H%M%S_%f')
        analysis_aoi=None
        if self.use_query_aoi.isChecked() and self.aoi_geometry:
            # Run the geometry shown in this session, not a possibly edited
            # external file originally used to import/export the same polygon.
            import hashlib
            digest=hashlib.sha256(json.dumps(self.aoi_geometry,sort_keys=True).encode()).hexdigest()
            path=self.workspace/'spatial_objects'/('aoi_'+digest+'.geojson')
            write_json(path,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'role':'analysis AOI'},'geometry':self.aoi_geometry}]})
            analysis_aoi=str(path.resolve())
        return {'epochs':entries,'output':str(out),'project_id':self.project_id,'case_title':self.project_title.text(),
                'method':self.method.currentData(),'network':self.network_mode.currentData(),
                'resolution':self.resolution.value(),'block_pixels':self.block_size.value(),'max_shift_m':self.shift_limit.value(),
                'stable_mask':self.stable_path.text().strip() or None,'validation_mask':self.validation_path.text().strip() or None,
                'require_match':self.require_match.isChecked(),'datum_confirmed':self.datum_confirmed.isChecked(),
                'bbox':self.bbox() if self.use_query_aoi.isChecked() else None,'analysis_aoi':analysis_aoi}

    def process(self):
        cfg=self.guard(self.job)
        if cfg:
            operation=compare_registration_methods if cfg['method']=='compare' else run
            self.start('Processing epoch network…',lambda log,cancel:operation(cfg,log,cancel),self.processing_finished)

    def save_job(self):
        cfg=self.guard(self.job)
        if not cfg:return
        p,_=QFileDialog.getSaveFileName(self,'Job JSON',str(self.workspace/'job.json'),'JSON (*.json)')
        if p:write_json(p,cfg)

    def build_results(self):
        tab=QWidget();layout=QVBoxLayout(tab);row=QHBoxLayout()
        row.addWidget(self.button('Open results folder…',self.open_results));self.layer=QComboBox();self.layer.currentTextChanged.connect(self.show_result_layer);row.addWidget(self.layer,1)
        row.addWidget(self.button('Load sample point…',self.load_sample_point));row.addWidget(self.button('Export current point…',self.export_sample_point));row.addWidget(self.button('Show output directory',self.reveal_results));layout.addLayout(row)
        row=QHBoxLayout();row.addWidget(self.button('Store current point in case…',self.store_point));row.addWidget(self.button('Export case report…',self.export_case_report));row.addStretch();layout.addLayout(row)
        self.result_note=QLabel('Run an analysis or open a completed result folder. Click a map pixel to inspect its elevation history.');self.result_note.setWordWrap(True);layout.addWidget(self.result_note)
        split=QSplitter(Qt.Horizontal);self.result_panel=CanvasPanel();self.series_panel=CanvasPanel();split.addWidget(self.result_panel);split.addWidget(self.series_panel);split.setSizes([800,400]);layout.addWidget(split,1)
        self.result_panel.canvas.mpl_connect('button_release_event',self.plot_timeseries)
        self.result_text=QPlainTextEdit();self.result_text.setReadOnly(True);self.result_text.setMaximumHeight(180);layout.addWidget(self.result_text)
        self.tabs.addTab(tab,'3  Results / time series')

    def build_network(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        self.network_note=QLabel('Closure diagnostics become available after stable-terrain registration. Raw differences from the same elevation stack close algebraically and are not used as a quality test.');self.network_note.setWordWrap(True);layout.addWidget(self.network_note)
        split=QSplitter(Qt.Horizontal);self.network_panel=CanvasPanel();split.addWidget(self.network_panel)
        right=QWidget();rl=QVBoxLayout(right)
        rl.addWidget(QLabel('Independent pair translations and network residuals'))
        self.edge_table=QTableWidget(0,6);self.edge_table.setHorizontalHeaderLabels(['Edge','Sample dx (m)','Sample dy (m)','Add dz (m)','Residual norm (m)','Held-out NMAD (m)']);self.edge_table.setEditTriggers(QTableWidget.NoEditTriggers);rl.addWidget(self.edge_table)
        rl.addWidget(QLabel('Fundamental cycles BEFORE network adjustment'))
        self.cycle_table=QTableWidget(0,5);self.cycle_table.setHorizontalHeaderLabels(['Cycle','Closure dx (m)','Closure dy (m)','Closure dz (m)','Norm (m)']);self.cycle_table.setEditTriggers(QTableWidget.NoEditTriggers);rl.addWidget(self.cycle_table)
        split.addWidget(right);split.setSizes([500,800]);layout.addWidget(split,1);self.tabs.addTab(tab,'4  Network / closure')

    def show_network(self,path,report):
        ax=self.network_panel.ax;ax.clear();self.edge_table.setRowCount(0);self.cycle_table.setRowCount(0)
        if not (path/'network.json').exists():
            self.network_note.setText('Network closure was not evaluated for this raw DoD run.');self.network_panel.canvas.draw_idle();return
        net=json.loads((path/'network.json').read_text());edges=json.loads((path/'registration_edges.json').read_text())['accepted'];n=len(report['epochs'])
        angles=np.linspace(np.pi/2,np.pi/2+2*np.pi,n,endpoint=False);points=np.column_stack([np.cos(angles),np.sin(angles)])
        residuals={(r['i'],r['j']):r for r in net['edge_residuals']};maximum=max([r['residual_norm_m'] for r in net['edge_residuals']]+[.001])
        from matplotlib import colormaps
        for e in edges:
            i,j=e['i'],e['j'];res=residuals[i,j]['residual_norm_m'];ax.plot(points[[i,j],0],points[[i,j],1],color=colormaps['YlOrRd'](.2+.7*res/maximum),linewidth=1.8,zorder=1)
        ax.scatter(points[:,0],points[:,1],s=400,color='#1a7887',zorder=2)
        for i,p in enumerate(points):
            ax.text(*p,str(i),color='white',ha='center',va='center',fontweight='bold')
            offset=22 if abs(p[0])>.7 or p[1]>0 else -24
            ax.annotate(report['epochs'][i]['date'][:10],p,xytext=(0,offset),textcoords='offset points',ha='center',va='center',fontsize=9)
        ax.set_xlim(-1.5,1.5);ax.set_ylim(-1.45,1.45);ax.set_aspect('equal');ax.axis('off');self.network_panel.canvas.draw_idle()
        self.edge_table.setRowCount(len(edges))
        for row,e in enumerate(edges):
            vals=[f"{e['i']} → {e['j']}",e['sampling_dx_m'],e['sampling_dy_m'],e['add_dz_m'],residuals[e['i'],e['j']]['residual_norm_m'],e['after']['nmad_m']]
            for c,v in enumerate(vals):self.edge_table.setItem(row,c,QTableWidgetItem(f'{v:.4f}' if isinstance(v,float) else str(v)))
        self.cycle_table.setRowCount(len(net['cycle_basis']))
        for row,e in enumerate(net['cycle_basis']):
            for c,k in enumerate(['cycle','closure_dx_m','closure_dy_m','closure_dz_m','closure_norm_m']):
                v=e[k];self.cycle_table.setItem(row,c,QTableWidgetItem(f'{v:.4f}' if isinstance(v,float) else str(v)))
        self.edge_table.resizeColumnsToContents();self.cycle_table.resizeColumnsToContents()
        self.network_note.setText(f"{n} epochs · {len(edges)} accepted edges · {net['cycle_rank']} independent cycles. Node 0 anchors the relative network. Edge colour scales with residual magnitude, not statistical significance. Closure cannot detect all common-mode or node-consistent errors.")

    def build_log(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        row=QHBoxLayout();row.addWidget(self.button('Collect current workspace ZIP',self.collect_current_results))
        row.addWidget(self.button('Show ZIP folder',self.show_bundle_folder));row.addStretch();layout.addLayout(row)
        self.last_bundle=None
        self.bundle_info=QLabel('Collects logs, tables, reports and current GUI settings. Large rasters and external references are omitted; nothing is uploaded.')
        self.bundle_info.setWordWrap(True);layout.addWidget(self.bundle_info)
        scientific=QHBoxLayout()
        self.validation_profile=QComboBox();self.validation_profile.addItem('Quick: 8 scenes / 32 records','quick')
        self.validation_profile.addItem('Extended: 48 scenes / 192 records','extended')
        scientific.addWidget(self.validation_profile)
        scientific.addWidget(self.button('Run scientific validation',self.run_scientific_validation))
        scientific.addWidget(self.button('Open validation report',self.open_validation_report))
        scientific.addStretch();layout.addLayout(scientific)
        self.last_validation=None
        note=QLabel('Offline known-truth experiments: offsets, noise, missing data and expected failures. Uses a separate output folder in the current workspace.')
        note.setWordWrap(True);layout.addWidget(note)
        self.log_text=QPlainTextEdit();self.log_text.setReadOnly(True);layout.addWidget(self.log_text);self.tabs.addTab(tab,'5  Logs')

    def run_scientific_validation(self):
        from .validation_suite import run_benchmark,new_output
        output=new_output(self.workspace);profile=self.validation_profile.currentData()
        self.start('Scientific validation: '+profile,
                   lambda log,cancel:run_benchmark(output,profile,log,cancel),self.scientific_validation_finished)

    def scientific_validation_finished(self,result):
        self.last_validation=result['html']
        self.log(f"Scientific validation completed; {result['summary']['unexpected_checks']} unexpected checks. Report: {result['html']}")

    def open_validation_report(self):
        if self.last_validation and Path(self.last_validation).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_validation))
        else:self.log('Run scientific validation first, or open an existing benchmark_report.html from its output folder.')

    def processing_finished(self,report):
        self.load_results(Path(report['output']));self.tabs.setCurrentIndex(2)

    def open_results(self):
        p=QFileDialog.getExistingDirectory(self,'Completed results folder',str(self.workspace))
        if p:self.guard(lambda:self.load_results(Path(p)))

    def load_results(self,path):
        report=json.loads((path/'report.json').read_text(encoding='utf-8'))
        self.result_dir=path;self.result_report=report
        self.series_panel.ax.clear();self.series_panel.ax.set_xlabel('Acquisition date');self.series_panel.ax.set_ylabel('Surface height (m)');self.series_panel.canvas.draw_idle()
        self.layer.blockSignals(True);self.layer.clear();self.layer.addItems([p.name for p in sorted(path.glob('*.tif')) if p.name!='epoch_stack.tif']);self.layer.blockSignals(False)
        desired=next((p.name for p in sorted(path.glob('dod_00_*.tif'),reverse=True)),self.layer.itemText(0));self.layer.setCurrentText(desired);self.show_result_layer(desired)
        rank=report.get('network_cycle_rank');self.result_note.setText(f"{len(report['epochs'])} epochs | {report['method']} | independent cycle count: {rank if rank is not None else 'not evaluated'}. Click a map pixel for its time series.")
        location=str(path)
        if report.get('comparison_root'):location+='\nComparison root: '+report['comparison_root']
        self.result_text.setPlainText('\n'.join(report['warnings'])+'\n\n'+location)
        self.show_network(path,report)
        if self.current_point:
            from pyproj import Transformer
            import rasterio
            with rasterio.open(path/'epoch_stack.tif') as src:target_crs=src.crs
            x,y,crs=self.current_point;x,y=Transformer.from_crs(crs,target_crs,always_xy=True).transform(x,y)
            self.show_timeseries_at(x,y)

    def show_result_layer(self,name):
        if not self.result_dir or not name:return
        data,extent,crs=read_preview(self.result_dir/name);panel=self.result_panel;panel.fig.clear();panel.ax=panel.fig.add_subplot(111)
        diverging=name.startswith(('dod_','raw_dod_','average_rate_','descriptive_ols'))
        finite=data[np.isfinite(data)];kwargs={}
        if diverging:
            lim=max(float(np.quantile(np.abs(finite),.98)),.1) if finite.size else 1;kwargs={'vmin':-lim,'vmax':lim}
        im=panel.ax.imshow(data,extent=extent,cmap='RdBu' if diverging else 'viridis',origin='upper',**kwargs)
        label='Elevation difference (m)' if name.startswith(('dod_','raw_dod_')) else 'Rate (m/year)' if name.startswith(('average_rate_','descriptive_ols')) else 'Valid epoch count' if name=='valid_epoch_count.tif' else 'Time span (years)' if name=='observation_span_years.tif' else 'Class code'
        panel.fig.colorbar(im,ax=panel.ax,shrink=.85,label=label,extend='both' if diverging else 'neither');panel.ax.set_xlabel('EPSG:3413 easting (m)');panel.ax.set_ylabel('Northing (m)')
        from matplotlib.ticker import MaxNLocator, ScalarFormatter
        formatter=ScalarFormatter(useOffset=True);formatter.set_powerlimits((-4,4))
        panel.ax.xaxis.set_major_locator(MaxNLocator(5));panel.ax.yaxis.set_major_locator(MaxNLocator(5))
        panel.ax.xaxis.set_major_formatter(formatter);panel.ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=True));panel.toolbar.update();panel.canvas.draw_idle()

    def plot_timeseries(self,event):
        if not self.result_dir or event.inaxes!=self.result_panel.ax or event.xdata is None:return
        if event.button!=1 or self.result_panel.toolbar.mode or self.result_panel.last_pan_was_drag:return
        self.show_timeseries_at(event.xdata,event.ydata)

    def show_timeseries_at(self,x,y):
        import rasterio
        from .common import parse_date
        if not np.isfinite(x) or not np.isfinite(y):raise ValueError('Point cannot be transformed to result CRS.')
        with rasterio.open(self.result_dir/'epoch_stack.tif') as src:
            row,col=src.index(x,y);inside=0<=row<src.height and 0<=col<src.width
            vals=next(src.sample([(x,y)],masked=True)).astype('float32').filled(np.nan) if inside else np.full(src.count,np.nan)
            vals[vals==src.nodata]=np.nan
            crs=str(src.crs)
        dates=[parse_date(e['date']) for e in self.result_report['epochs']]
        ax=self.series_panel.ax;ax.clear();ax.plot(dates,vals,'o-',color='#197d88',markersize=6);ax.set_ylabel('Surface height (m)');ax.set_xlabel('Acquisition date');ax.grid(alpha=.2);self.series_panel.fig.autofmt_xdate();self.series_panel.canvas.draw_idle()
        self.current_point=(float(x),float(y),crs)
        marker=getattr(self,'point_marker',None)
        if marker is not None and marker.axes is self.result_panel.ax:marker.remove()
        if inside:self.point_marker=self.result_panel.ax.scatter([x],[y],marker='+',s=90,color='black',linewidths=1.5,zorder=5)
        self.result_panel.canvas.draw_idle()
        point_status=f'{np.isfinite(vals).sum()}/{len(vals)} valid epochs' if inside else 'outside result extent; not moved'
        self.result_note.setText(f"{len(self.result_report['epochs'])} epochs | {self.result_report['method']} | fixed point: ({x:.3f}, {y:.3f}) {crs} | {point_status}.")

    def export_sample_point(self):
        if not self.current_point:QMessageBox.information(self,'Sample point','Click a valid map pixel or load a point first.');return
        p,_=QFileDialog.getSaveFileName(self,'Export current sample point',str(self.workspace/'sample_point.geojson'),'GeoJSON (*.geojson)')
        if not p:return
        from pyproj import Transformer
        x,y,crs=self.current_point;lon,lat=Transformer.from_crs(crs,4326,always_xy=True).transform(x,y)
        write_json(p,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'role':'reusable time-series sample point','source_crs':crs,'source_x':x,'source_y':y},'geometry':{'type':'Point','coordinates':[lon,lat]}}]})
        self.log(f'Sample point exported: {Path(p).name}')

    def load_sample_point(self):
        if not self.result_dir:QMessageBox.information(self,'Results needed','Open or run a result first.');return
        p,_=QFileDialog.getOpenFileName(self,'Load WGS84 sample point',str(self.workspace),'GeoJSON (*.geojson *.json)')
        if not p:return
        def load():
            obj=json.loads(Path(p).read_text(encoding='utf-8-sig'));feature=obj['features'][0] if obj.get('type')=='FeatureCollection' else obj
            geom=feature['geometry'] if feature.get('type')=='Feature' else feature
            if geom.get('type')!='Point':raise ValueError('Sample file must contain a WGS84 GeoJSON Point.')
            import rasterio
            from pyproj import Transformer
            with rasterio.open(self.result_dir/'epoch_stack.tif') as src:crs=str(src.crs)
            x,y=Transformer.from_crs(4326,crs,always_xy=True).transform(*geom['coordinates'][:2])
            self.show_timeseries_at(x,y);self.log(f'Sample point loaded: {Path(p).name}')
        self.guard(load)

    def reveal_results(self):
        if self.result_dir:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_dir)))

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.cancel_task();QMessageBox.information(self,'Task running','Cancellation requested. Close the window after the current operation stops.');event.ignore()
        elif self.confirm_case_replace():event.accept()
        else:event.ignore()

def launch(workspace=None,project=None):
    app=QApplication.instance() or QApplication(sys.argv);app.setStyle('Fusion');app.setFont(QFont('Segoe UI',10))
    window=Window(workspace)
    if project:window.restore_case(project)
    window.show();return app.exec()
