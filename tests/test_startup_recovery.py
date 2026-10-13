"""Targeted checks for startup order and read-only acceptance recovery."""
import contextlib
import ctypes
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from arcticdem_workbench import windows_runtime as runtime
from tools import resume_release_gui as recovery
from tools.run_paper_release import collect


def pe_fixture():
    data=bytearray(1024);data[:2]=b'MZ'
    struct.pack_into('<I',data,60,128);data[128:132]=b'PE\0\0'
    struct.pack_into('<H',data,134,1);struct.pack_into('<H',data,148,240)
    struct.pack_into('<H',data,152,0x20b)
    struct.pack_into('<II',data,152+112+8,0x1000,40)
    struct.pack_into('<III',data,392+12,0x1000,512,512)
    struct.pack_into('<5I',data,512,0,0,0,0x1040,0x1080)
    data[576:589]=b'libexpat.dll\0'
    return bytes(data)


def saved_fixture(workspace):
    root=workspace/'paper_release_acceptance/20261010_102856_021515'
    root.mkdir(parents=True)
    status={'release':'0.11.0','status':'failed',
        'source_kind':'synthetic_release_acceptance',
        'candidate_engine_sha256':recovery.FROZEN_JOINT_SHA256,
        'checks':dict.fromkeys(recovery.REQUIRED_CHECKS,True),
        'error':'DLL load failed while importing pyexpat'}
    files={'acceptance_status.json':json.dumps(status),
        'acceptance_case.arcticdem.json':'{"fixture":true}',
        'joint_result/report.json':'{"status":"completed"}',
        'joint_result/epoch_stack.tif':'saved raster fixture',
        'four_method_comparison/comparison_report.json':'{"methods":[]}',
        'common_support_report/report.html':'<p>Saved report fixture</p>'}
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data)
    collect(root)
    return root


class RuntimeTests(unittest.TestCase):
    def test_pe_expat_dependency_is_read_without_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pyexpat.pyd';path.write_bytes(pe_fixture())
            self.assertEqual(runtime.pe_import_names(path),['libexpat.dll'])
            path.write_bytes(b'ELF other platform')
            self.assertEqual(runtime.pe_import_names(path),[])
            path.write_bytes(pe_fixture()[:160])
            with self.assertRaises(ValueError):runtime.pe_import_names(path)

    def test_environment_expat_loaded_before_xml_and_qt_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp);pyside=prefix/'Lib/site-packages/PySide6'
            for path in (prefix/'Library/bin',prefix/'DLLs',pyside/'Qt/bin'):
                path.mkdir(parents=True,exist_ok=True)
            binary=prefix/'DLLs/pyexpat.pyd';binary.write_bytes(pe_fixture())
            (prefix/'Library/bin/libexpat.dll').write_bytes(b'fake DLL for load-order check')
            trace=[];handle=object()
            def add(path):trace.append(('add',path));return handle
            def load(path,winmode):trace.append(('preload',path));self.assertEqual(winmode,0x1100);return handle
            def imported(name):
                trace.append(('import',name))
                return SimpleNamespace(__file__=str(binary),EXPAT_VERSION='fixture')
            def spec(name):
                return SimpleNamespace(origin=str(binary)) if name=='pyexpat' else SimpleNamespace(submodule_search_locations=[str(pyside)])
            initial_handles=len(runtime._DLL_HANDLES);initial_libs=len(runtime._LOADED_LIBRARIES)
            with patch.object(sys,'platform','win32'),patch.object(sys,'prefix',str(prefix)), \
                 patch.object(runtime.os,'add_dll_directory',side_effect=add,create=True), \
                 patch.object(runtime.importlib.util,'find_spec',side_effect=spec), \
                 patch.object(runtime.importlib,'import_module',side_effect=imported), \
                 patch.object(ctypes,'WinDLL',side_effect=load,create=True), \
                 patch.dict(runtime.os.environ,{'PATH':'original'},clear=False):
                result=runtime.prepare_runtime()
                self.assertEqual(result['status'],'passed')
                self.assertTrue(runtime.os.environ['QT_PLUGIN_PATH'].startswith(str(pyside)))
            operations=[x[0]+':'+x[1] for x in trace]
            preload=next(i for i,x in enumerate(trace) if x[0]=='preload')
            xml=trace.index(('import','pyexpat'))
            qt=next(i for i,x in enumerate(trace) if x[0]=='add' and x[1]==str(pyside))
            self.assertLess(preload,xml);self.assertLess(xml,qt)
            self.assertGreater(len(runtime._DLL_HANDLES),initial_handles)
            self.assertGreater(len(runtime._LOADED_LIBRARIES),initial_libs)
            del runtime._DLL_HANDLES[initial_handles:];del runtime._LOADED_LIBRARIES[initial_libs:]

    def test_failed_xml_import_records_diagnostics_and_never_configures_qt(self):
        info={}
        with patch.object(sys,'platform','linux'), \
             patch.object(runtime.importlib,'import_module',side_effect=ImportError('controlled XML error')), \
             patch.object(runtime.importlib.util,'find_spec') as qt:
            with self.assertRaises(ImportError):runtime.prepare_runtime(info)
            qt.assert_not_called()
        self.assertEqual(info['status'],'failed');self.assertIn('controlled XML error',info['error'])


class RecoveryTests(unittest.TestCase):
    def test_gui_failure_can_reuse_completed_calculations_with_exact_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'work';root=saved_fixture(workspace)
            selected,status=recovery.find_saved_run(workspace)
            self.assertEqual(selected,root)
            self.assertEqual(status['status'],'failed')
            self.assertEqual(recovery.verify_saved_run(root)['sha256_checks'],'passed')

    def test_changed_saved_result_is_rejected_before_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=saved_fixture(Path(tmp)/'work')
            (root/'joint_result/epoch_stack.tif').write_text('changed raster')
            with self.assertRaisesRegex(ValueError,'Saved acceptance changed'):
                recovery.verify_saved_run(root)

    def test_recovery_failure_preserves_source_and_bundles_without_fitting(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'work';root=saved_fixture(workspace)
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(sys,'argv',['resume_release_gui.py','--workspace',str(workspace)]), \
                 patch.object(runtime,'prepare_runtime',return_value={'status':'passed'}), \
                 patch.object(recovery,'gui_session',side_effect=ImportError('controlled GUI import error')), \
                 patch('tools.run_paper_release.acceptance',side_effect=AssertionError('must not refit')), \
                 contextlib.redirect_stdout(io.StringIO()):
                code=recovery.main()
            self.assertEqual(code,1)
            after={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(after,before)
            archive=next((workspace/'paper_release_recovery').glob('UPLOAD_TO_CHATGPT_GUI_RECOVERY_*.zip'))
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                status=json.loads(z.read('recovery_status.json'))
                self.assertFalse(status['computations_repeated'])
                self.assertEqual(status['source_release'],'0.11.0')
                self.assertIn('controlled GUI import error',status['traceback'])
                self.assertEqual(z.read('saved_acceptance/joint_result/epoch_stack.tif'),before['joint_result/epoch_stack.tif'])

    def test_no_completed_source_returns_diagnostic_without_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'work'
            with patch.object(sys,'argv',['resume_release_gui.py','--workspace',str(workspace)]), \
                 patch('tools.run_paper_release.acceptance',side_effect=AssertionError('must not generate inputs')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(recovery.main(),1)
            self.assertTrue(list((workspace/'paper_release_recovery').glob('*.zip')))


if __name__=='__main__':unittest.main()
