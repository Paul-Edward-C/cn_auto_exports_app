"""Process-wide data shared by ALL panels (China trade, Auto trade, …).

Bokeh re-executes ``main.py`` for every new browser session, so anything done at module
level there would repeat per page load. Everything imported from this module (and from
``shared_data_cn``/``shared_data_auto``) runs ONCE per dyno — Python caches imported
modules in ``sys.modules`` — and is shared read-only across all sessions.

This module holds only what BOTH panels need: house-style constants, the colour palette,
the world-map geometry, and the iso3 -> region lookup. Per-panel parquet data lives in
the panel-specific shared_data modules.
"""
from pathlib import Path
import base64
import json
import numpy as np
import pandas as pd

HERE = Path(__file__).parent

# ---------------------------------------------------------------- house style
# East Asia Econ 2025 identity: forest green + cream + sage, serif display (bamboo logo).
FONT = 'Georgia'
BRAND = '#1f4d3a'          # forest green — primary brand (headings, tabs, table header, accents)
SAGE = '#6f9b60'           # sage green — secondary accent / hovers / borders
CREAM = '#f5efe1'          # cream — light text on green, alternating table rows
PANEL_BG = '#ffffff'       # chart/map background (was warm cream #f6f2e9)
MAX_SERIES = 4
SERIES_COLORS = ['#1f4d3a', '#B7410E', '#6f9b60', '#4682B4']
CHART_W, CHART_H = 972, 589
_RAMP = ['#87CEEB', '#4682B4', '#FFDB58', '#FFBF00', '#FF7F50', '#B7410E', '#CD5C5C']


def _ramp_palette(stops, n=256):
    """256-stop hex ramp by linear RGB interpolation (avoids importing matplotlib)."""
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in stops], float)
    xs, xi = np.linspace(0, 1, len(stops)), np.linspace(0, 1, n)
    out = np.stack([np.interp(xi, xs, rgb[:, c]) for c in range(3)], axis=1).round().astype(int)
    return ['#%02x%02x%02x' % tuple(c) for c in out]


PALETTE = _ramp_palette(_RAMP)
# The chart watermark, matching the toolsite charts (ghost/toolsite): the brand lockup PNG
# (800x460) at 10% alpha across 90% of the plot frame (capped at 72% of its height), centred
# horizontally and a little above middle (45% down) so it clears a top-left legend. No text.
# Embedded as a same-origin data: URI: an external image taints the plot canvas and breaks the
# Save tool's PNG export. The PNG is the toolsite's own WM constant.
# On the white background the logo uses watermark_white.png: the toolsite PNG's shape filled with
# the brand sage (#6f9b60) at 22% over white (a light sage, RGB 223,233,220), drawn at full
# alpha so its edges fade to white. (watermark.png = the original toolsite PNG.)
_WM_FILE = HERE / 'data' / 'watermark_white.png'
WATERMARK_URL = 'data:image/png;base64,' + base64.b64encode(_WM_FILE.read_bytes()).decode('ascii')
WM_ASPECT, WM_ALPHA = 800 / 460, 1.0


def add_watermark(fig):
    """Place the brand watermark behind fig's data, toolsite-style. Geometry is in screen
    terms, so it is recomputed in the browser whenever the ranges or frame size change."""
    from bokeh.models import ColumnDataSource, CustomJS
    src = ColumnDataSource(dict(url=[WATERMARK_URL], x=[0], y=[0], w=[0], h=[0]))
    fig.image_url(url='url', x='x', y='y', w='w', h='h', source=src, anchor='center',
                  global_alpha=WM_ALPHA, level='underlay')
    cb = CustomJS(args=dict(fig=fig, src=src, aspect=WM_ASPECT), code="""
        const xr = fig.x_range, yr = fig.y_range;
        const fw = fig.inner_width, fh = fig.inner_height;
        if (!fw || !fh || xr.start == null || yr.start == null) return;
        let ww = fw * 0.90, wh = ww / aspect;
        if (wh > fh * 0.72) { wh = fh * 0.72; ww = wh * aspect; }
        const sx = (xr.end - xr.start) / fw, sy = (yr.end - yr.start) / fh;
        src.data = {url: src.data.url, x: [xr.start + fw / 2 * sx], y: [yr.end - fh * 0.45 * sy],
                    w: [ww * sx], h: [wh * sy]};
    """)
    for rng in (fig.x_range, fig.y_range):
        rng.js_on_change('start', cb)
        rng.js_on_change('end', cb)
    fig.js_on_change('inner_width', cb)
    fig.js_on_change('inner_height', cb)
    return src

# ---------------------------------------------------------------- world geometry (shared)
_WORLD = pd.read_parquet(HERE / 'data' / 'world_patches.parquet')
WORLD_XS = [list(x) for x in _WORLD['xs']]
WORLD_YS = [list(y) for y in _WORLD['ys']]
WORLD_ISO = list(_WORLD['iso3'])
WORLD_NAME = list(_WORLD['name'])
N_PATCH = len(WORLD_ISO)
COUNTRY_NAMES_SORTED = sorted(WORLD_NAME)
ISO_IDX = {iso: j for j, iso in enumerate(WORLD_ISO)}
COUNTRY_ISO = dict(zip(WORLD_NAME, WORLD_ISO))

# iso3 -> primary geographic region (shared by both panels' Region dropdown).
REGION_OF = json.loads((HERE / 'data' / 'region_map.json').read_text())

# Region membership by map patch index (for the Region dropdown's group highlight).
REGION_MEMBER_IDX = {}
for _j, _iso in enumerate(WORLD_ISO):
    _r = REGION_OF.get(_iso)
    if _r:
        REGION_MEMBER_IDX.setdefault(_r, []).append(_j)

del _WORLD
