from __future__ import annotations
import csv
import hashlib
import json
import platform
import os
import ssl
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(path)

def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0]) if rows else (fields or [])
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def versions():
    import importlib.metadata as md
    from . import __version__
    data = {"workbench": __version__, "python": sys.version.split()[0], "platform": platform.platform()}
    for name in ("numpy", "scipy", "rasterio", "pyproj", "shapely", "matplotlib", "PySide6-Essentials"):
        try:
            data[name] = md.version(name)
        except md.PackageNotFoundError:
            data[name] = "not installed"
    return data

def check_cancel(cancel):
    if cancel and cancel():
        raise InterruptedError("Operation cancelled; completed downloads remain reusable.")

def parse_date(value):
    value=datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is not None:value=value.astimezone(timezone.utc)
    return value.replace(tzinfo=None)

def tls_bundle():
    """Standard public roots plus explicitly configured/OS trust; verification stays enabled."""
    import certifi
    data=Path(certifi.where()).read_bytes()
    candidate=os.environ.get('ARCTICDEM_CA_BUNDLE') or os.environ.get('SSL_CERT_FILE') or ssl.get_default_verify_paths().cafile
    if candidate:
        if not Path(candidate).is_file():raise ValueError('Configured CA certificate bundle does not exist.')
        data+=b'\n'+Path(candidate).read_bytes()
    if os.name=='nt':
        for der in ssl.create_default_context().get_ca_certs(binary_form=True):
            data+=b'\n'+ssl.DER_cert_to_PEM_cert(der).encode('ascii')
    digest=hashlib.sha256(data).hexdigest()
    directory=Path(tempfile.gettempdir())/'arcticdem_workbench_ca';directory.mkdir(exist_ok=True)
    path=directory/(digest+'.pem')
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=directory,delete=False) as f:
            f.write(data);temporary=Path(f.name)
        temporary.replace(path)
    return str(path)
