"""Process-local Windows DLL setup, before Qt or scientific extension imports.

Does not install packages, move DLLs, or change permanent environment settings.
"""
from __future__ import annotations
import importlib
import importlib.util
import os
from pathlib import Path
import struct
import sys

_DLL_HANDLES = []
_LOADED_LIBRARIES = []


def pe_import_names(path):
    """Read the import names of a PE binary without loading that binary."""
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:2] != b'MZ':
        return []
    def u32(offset):
        if offset < 0 or offset+4 > len(data):
            raise ValueError('Truncated PE structure')
        return struct.unpack_from('<I', data, offset)[0]
    pe = u32(60)
    if pe+24 > len(data) or data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    section_count = struct.unpack_from('<H', data, pe+6)[0]
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe+24
    if optional_size < 2 or optional+optional_size > len(data):
        raise ValueError('Invalid PE optional header')
    magic = struct.unpack_from('<H', data, optional)[0]
    directory_offset = {0x10b:96, 0x20b:112}.get(magic)
    if directory_offset is None or optional_size < directory_offset+16:
        return []
    import_rva = u32(optional+directory_offset+8)
    if not import_rva:
        return []
    sections = []
    section_offset = optional+optional_size
    if section_count > 96 or section_offset+40*section_count > len(data):
        raise ValueError('Invalid PE section table')
    for index in range(section_count):
        item = section_offset+40*index
        sections.append((u32(item+12), u32(item+16), u32(item+20)))
    def file_offset(rva):
        for address, raw_size, raw_offset in sections:
            if address <= rva < address+raw_size:
                offset = raw_offset+rva-address
                if offset >= len(data):
                    raise ValueError('PE RVA outside file')
                return offset
        raise ValueError('PE import RVA outside raw sections')
    base = file_offset(import_rva)
    names = []
    for index in range(256):
        offset = base+20*index
        if offset+20 > len(data):
            raise ValueError('Truncated PE import table')
        descriptor = struct.unpack_from('<5I', data, offset)
        if not any(descriptor):
            return names
        name_offset = file_offset(descriptor[3])
        end = data.find(b'\0', name_offset, min(name_offset+260, len(data)))
        if end < 0:
            raise ValueError('Unterminated PE DLL name')
        name = data[name_offset:end].decode('ascii')
        if '/' in name or '\\' in name or ':' in name:
            raise ValueError('PE DLL name must be a basename')
        names.append(name)
    raise ValueError('PE import table exceeds diagnostic limit')


def prepare_runtime(record=None):
    """Register trusted environment directories; load Expat before adding Qt.

    Retain directory/library handles for the process lifetime. The interpreter
    prefix is authoritative, rather than a potentially stale CONDA_PREFIX.
    """
    info = record if record is not None else {}
    info.update(status='starting', platform=sys.platform,
                executable=sys.executable, prefix=sys.prefix,
                isolated=bool(sys.flags.isolated),
                permanent_environment_changes=False, package_installation=False,
                dll_directories=[], expat_preloads=[])
    try:
        prefix = Path(sys.prefix)
        if sys.platform == 'win32':
            for directory in (prefix/'Library/bin', prefix/'DLLs', prefix):
                if directory.is_dir():
                    _DLL_HANDLES.append(os.add_dll_directory(str(directory.resolve())))
                    info['dll_directories'].append(str(directory.resolve()))
            # Some dependencies may be found in System32 before AddDllDirectory
            # locations. Preload only the Expat DLL names actually requested by
            # this interpreter's pyexpat binary, using absolute environment paths.
            spec = importlib.util.find_spec('pyexpat')
            if spec and spec.origin and Path(spec.origin).is_file():
                info['pyexpat_binary'] = spec.origin
                dependencies = pe_import_names(spec.origin)
                info['pyexpat_dependency_names'] = dependencies
                for name in dependencies:
                    if 'expat' not in name.lower():
                        continue
                    candidate = prefix/'Library/bin'/name
                    if not candidate.is_file():
                        info.setdefault('missing_environment_expat_dependencies', []).append(str(candidate))
                        continue
                    import ctypes
                    library = ctypes.WinDLL(str(candidate.resolve()), winmode=0x1100)
                    _LOADED_LIBRARIES.append(library)
                    info['expat_preloads'].append(str(candidate.resolve()))
        pyexpat = importlib.import_module('pyexpat')
        importlib.import_module('plistlib')
        info['pyexpat_import'] = 'passed'
        info['pyexpat_origin'] = getattr(pyexpat, '__file__', None)
        info['expat_version'] = getattr(pyexpat, 'EXPAT_VERSION', None)
        # Configure the Qt wheel only after Python's XML dependency is loaded.
        spec = importlib.util.find_spec('PySide6')
        if spec and spec.submodule_search_locations:
            pyside = Path(next(iter(spec.submodule_search_locations)))
            info['pyside_directory'] = str(pyside)
            if sys.platform == 'win32':
                for directory in (pyside, pyside/'Qt/bin'):
                    if directory.is_dir():
                        _DLL_HANDLES.append(os.add_dll_directory(str(directory.resolve())))
                        info['dll_directories'].append(str(directory.resolve()))
                os.environ['PATH'] = str(pyside)+os.pathsep+os.environ.get('PATH', '')
                os.environ['QT_PLUGIN_PATH'] = str(pyside/'plugins')
                os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(pyside/'plugins/platforms')
        info['status'] = 'passed'
        return info
    except Exception as exc:
        info.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
