"""Published-case entry points and local result collection."""
from __future__ import annotations
import json
from datetime import datetime
from html import escape
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextBrowser, QComboBox, QFileDialog)
from .cases import load_cases, create_case, query_objects
from .common import write_json


class CaseLibraryMixin:
    def build_case_library(self):
        self.case_catalogue = load_cases()
        tab = QWidget(); layout = QVBoxLayout(tab)
        note = QLabel('Published-study starting points. Create a separate case workspace, then verify actual acquisition dates, '
                      'valid overlap and reference terrain. Templates contain no DEMs or validated result values.')
        note.setWordWrap(True); layout.addWidget(note)
        self.case_table = QTableWidget(0,4)
        self.case_table.setHorizontalHeaderLabels(['Site','Process','Reference','Pilot search interval'])
        self.case_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.case_table.setSelectionMode(QTableWidget.SingleSelection)
        self.case_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.case_table.setAlternatingRowColors(True)
        self.case_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.case_table.setMaximumHeight(155)
        self.case_table.setRowCount(len(self.case_catalogue))
        for row, case in enumerate(self.case_catalogue):
            for col, text in enumerate((case['name'],case['process'],case['reference_label'],case['start']+' to '+case['end'])):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole,case['id']); self.case_table.setItem(row,col,item)
        layout.addWidget(self.case_table)
        self.case_details = QTextBrowser(); self.case_details.setOpenExternalLinks(False)
        layout.addWidget(self.case_details,1)
        row = QHBoxLayout()
        row.addWidget(self.button('Create case workspace…',self.start_published_case))
        row.addWidget(self.button('Export pilot AOI…',self.export_pilot_aoi))
        self.case_reference = QComboBox(); row.addWidget(self.case_reference,1)
        row.addWidget(self.button('Open reference',self.open_case_reference))
        layout.addLayout(row)
        self.tabs.addTab(tab,'7  Published cases')
        self.case_table.itemSelectionChanged.connect(self.describe_published_case)
        self.case_table.selectRow(0)

    def selected_published_case(self):
        row = self.case_table.currentRow()
        if row < 0: return None
        cid = self.case_table.item(row,0).data(Qt.UserRole)
        return next(c for c in self.case_catalogue if c['id']==cid)

    def describe_published_case(self):
        case = self.selected_published_case()
        if case is None:return
        e = escape
        parts = ['<h2>'+e(case['name'])+'</h2>',
                 '<p><b>Status:</b> candidate for testing; scientific validation pending.</p>',
                 '<p><b>Pilot AOI (W, S, E, N):</b> '+e(', '.join(map(str,case['bbox'])))+'</p>',
                 '<p>'+e(case['location_basis'])+'</p>',
                 '<p>'+e(case['study_context'])+'</p>']
        for title, key in [('Select epochs','epoch_guidance'),('Choose reference terrain','registration_guidance')]:
            parts.append('<h3>'+title+'</h3><p>'+e(case[key])+'</p>')
        for title,key in [('Comparable quantities','compare_metrics'),('Match the measurement definition','not_equivalent'),('Next actions','first_steps')]:
            parts.append('<h3>'+title+'</h3><ul>'+''.join('<li>'+e(x)+'</li>' for x in case[key])+'</ul>')
        parts.append('<h3>Primary references</h3>')
        for ref in case['references']:
            parts.append('<p>'+e(ref['label'])+'<br>DOI: '+e(ref['doi'])+'<br>'+e(ref['evidence'])+'</p>')
        self.case_details.setHtml(''.join(parts))
        self.case_reference.clear()
        for ref in case['references']:self.case_reference.addItem(ref['label'],ref['url'])

    def start_published_case(self):
        if self.case_busy():return
        case = self.selected_published_case()
        if case is None:return
        parent = QFileDialog.getExistingDirectory(self,'Parent folder for a new case workspace',str(self.workspace))
        if not parent or not self.confirm_case_replace():return
        def operation():
            name = case['id']+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]
            path = create_case(case['id'],Path(parent)/name)
            self.restore_case(path)
            self.tabs.setCurrentIndex(0)
            self.log('Case template loaded. Inspect the pilot AOI, then Search catalogue. Saved to: '+str(path))
            return path
        return self.guard(operation)

    def export_pilot_aoi(self):
        case = self.selected_published_case()
        if case is None:return
        path,_ = QFileDialog.getSaveFileName(self,'Export original pilot query rectangle',
            str(self.workspace/(case['id']+'_pilot_aoi.geojson')),'GeoJSON (*.geojson)')
        if path:self.guard(lambda:write_json(path,query_objects(case)))

    def open_case_reference(self):
        url = self.case_reference.currentData()
        if url:QDesktopServices.openUrl(QUrl(url))

    def collect_current_results(self):
        if self.case_busy():return
        from .diagnostics import bundle
        def capture():
            # Capture on the GUI thread; workers must not read Qt controls.
            return json.loads(json.dumps({'format':'arcticdem-gui-session',
                'title':self.project_title.text(),'notes':self.project_notes.toPlainText(),
                'project_id':self.project_id,'state':self.capture_case()},allow_nan=False))
        session = self.guard(capture)
        if session is None:return
        workspace = self.workspace
        self.start('Collecting current workspace results…',
            lambda log,cancel:bundle(workspace,log,cancel,session),self.collection_finished)

    def collection_finished(self, path):
        self.last_bundle = Path(path)
        self.bundle_info.setText('ZIP ready: '+str(path))
        self.log('Result ZIP ready for review: '+str(path))

    def show_bundle_folder(self):
        if self.last_bundle and self.last_bundle.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_bundle.parent)))
