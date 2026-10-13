"""Dependency-light coverage preview for systems where Matplotlib cannot import.

This is a labelled, nearest-cell preview, not a replacement for the saved
full-resolution GeoTIFFs. No Matplotlib, Pillow, Qt or XML parser is imported.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path
import struct
import zlib

import numpy as np


def _png(rgb):
    """Encode a small RGB preview using PNG filter 0 and standard-library zlib."""
    rgb = np.ascontiguousarray(rgb, dtype='uint8')
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError('RGB preview required.')

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    raw = b''.join(b'\x00' + row.tobytes() for row in rgb)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _palette(n):
    anchors = np.array([[68, 1, 84], [59, 82, 139], [33, 145, 140],
                        [94, 201, 98], [253, 231, 37]], dtype=float)
    return np.column_stack([np.interp(np.linspace(0, 4, n), np.arange(5), anchors[:, c])
                            for c in range(3)]).round().astype('uint8')


def save_svg_overview(path, grid, domain, count, span, n):
    """Save two self-contained maps without entering the plotting import chain."""
    domain = np.asarray(domain, bool)
    count = np.asarray(count)
    span = np.asarray(span)
    if domain.shape != count.shape or domain.shape != span.shape or not 2 <= n <= 12:
        raise ValueError('Invalid coverage preview shapes or epoch count.')
    if domain.shape != (grid.height, grid.width):
        raise ValueError('Preview grid differs from coverage arrays.')
    if grid.transform.b or grid.transform.d or grid.transform.a <= 0 or grid.transform.e >= 0:
        raise ValueError('Coverage preview requires a north-up grid.')
    if not domain.any() or np.any((count[domain] < 0) | (count[domain] > n)):
        raise ValueError('Invalid coverage count values.')
    # Sample the cell nearest each preview-cell centre. This never feeds statistics.
    height, width = domain.shape
    scale = min(1., 480 / max(height, width))
    ph, pw = max(1, round(height * scale)), max(1, round(width * scale))
    rows = np.minimum(height - 1, ((np.arange(ph) + .5) * height / ph).astype(int))
    cols = np.minimum(width - 1, ((np.arange(pw) + .5) * width / pw).astype(int))
    take = np.ix_(rows, cols)
    d = domain[take]; c = count[take].astype(int); s = span[take]
    colors = _palette(n + 1); continuous = _palette(256)
    valid_span = domain & np.isfinite(span) & (count >= 2)
    vmax = float(span[valid_span].max()) if valid_span.any() else 1.
    vmax = max(vmax, 1e-6)
    count_rgb = np.full((ph, pw, 3), [233, 238, 242], dtype='uint8')
    count_rgb[d] = colors[c[d]]
    span_rgb = np.full_like(count_rgb, [233, 238, 242])
    good = d & np.isfinite(s) & (c >= 2)
    span_rgb[good] = continuous[np.clip(np.rint(s[good] / vmax * 255), 0, 255).astype(int)]
    l, b, r, t = grid.bounds
    rw, rh = r - l, t - b
    box_w, box_h = 404., 328.
    factor = min(box_w / rw, box_h / rh)
    map_w, map_h = rw * factor, rh * factor
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="620" viewBox="0 0 1120 620" role="img" aria-labelledby="title desc">',
             '<title id="title">Pre-registration quality-valid coverage</title>',
             '<desc id="desc">Nearest-cell preview. Full-resolution saved rasters determine all statistics. Grey means outside AOI or no temporal span.</desc>',
             '<rect width="1120" height="620" fill="white"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#17343c}.tick{font-size:11px}.label{font-size:13px}</style>']

    def txt(x, y, text, size=14, anchor='start'):
        parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}">{escape(str(text))}</text>')

    txt(28, 34, 'PRE-REGISTRATION COVERAGE', 23)
    txt(28, 58, 'Nearest-cell preview; statistics use the complete grid. No elevation change was measured.', 14)
    for index, (rgb, title) in enumerate([(count_rgb, 'Quality-valid acquisition dates'),
                                         (span_rgb, 'Observed time span (years, at least 2 dates)')]):
        panel_x = 28 + index * 552
        txt(panel_x, 94, title, 16)
        x = panel_x + 82 + (box_w - map_w) / 2
        y = 114 + (box_h - map_h) / 2
        data = base64.b64encode(_png(rgb)).decode('ascii')
        parts.append(f'<image x="{x:.3f}" y="{y:.3f}" width="{map_w:.3f}" height="{map_h:.3f}" preserveAspectRatio="none" style="image-rendering:pixelated" href="data:image/png;base64,{data}"/>')
        parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{map_w:.3f}" height="{map_h:.3f}" fill="none" stroke="#6e858e"/>')
        for fraction in (0, .5, 1):
            txt(x + map_w * fraction, y + map_h + 20, f'{l + rw * fraction:.0f}', 11, 'middle')
            txt(x - 6, y + map_h * (1 - fraction) + 4, f'{b + rh * fraction:.0f}', 11, 'end')
        txt(panel_x + 284, 483, str(grid.crs) + ' easting (m)', 13, 'middle')
        parts.append(f'<text x="{panel_x + 10}" y="285" font-size="13" text-anchor="middle" transform="rotate(-90 {panel_x + 10} 285)">Northing (m)</text>')
        palette = colors if index == 0 else continuous
        bar_x, bar_y, bar_w = panel_x + 82, 507, 404
        for k, color in enumerate(palette):
            x0 = bar_x + bar_w * k / len(palette)
            parts.append(f'<rect x="{x0:.3f}" y="{bar_y}" width="{bar_w / len(palette) + .02:.3f}" height="15" fill="rgb({color[0]},{color[1]},{color[2]})"/>')
        if index == 0:
            for k in range(n + 1):
                txt(bar_x + bar_w * (k + .5) / (n + 1), 539, k, 11, 'middle')
        else:
            for fraction in (0, .5, 1):
                txt(bar_x + bar_w * fraction, 539, f'{vmax * fraction:.2f}', 11, 'middle')
            if not valid_span.any():
                txt(panel_x + 82, 560, 'No pixels have two valid acquisition dates.', 12)
    txt(28, 585, 'Grey: outside AOI (left); outside AOI or fewer than 2 valid dates (right).', 13)
    txt(28, 608, 'Preview only: small gaps can be missed by display sampling. Use the GeoTIFF masks for measurement.', 12)
    parts.append('</svg>')
    Path(path).write_text('\n'.join(parts), encoding='utf-8', newline='\n')


def save_portable_overview(path, grid, domain, count, span, n):
    """Try the usual PNG, then a labelled SVG. Return the format and any warning."""
    from .coverage import save_overview
    path = Path(path)
    try:
        save_overview(path, grid, domain, count, span, n)
        return {'file': path.name, 'renderer': 'matplotlib', 'warning': None}
    except Exception as exc:
        path.unlink(missing_ok=True)  # Never expose a partially written PNG.
        svg = path.with_suffix('.svg')
        save_svg_overview(svg, grid, domain, count, span, n)
        return {'file': svg.name, 'renderer': 'numpy_stdlib_svg',
                'warning': 'PNG unavailable; SVG preview saved instead. Original plotting error: ' + str(exc)}
