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
PANEL_BG = '#f6f2e9'       # warm cream — chart/map background
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
# The chart background watermark. Embedded as a same-origin data: URI (from the local file)
# rather than an external https URL: an external image taints the plot canvas, so the browser
# blocks the Save tool's PNG export ("Enter filename" appears but nothing downloads). A data:
# URI is same-origin and never taints, so Save works. Refresh with:
#   curl -o app/data/background.jpeg <image-url>
_BG_FILE = HERE / 'data' / 'background.jpeg'
BACKGROUND_URL = ('data:image/jpeg;base64,'
                  + base64.b64encode(_BG_FILE.read_bytes()).decode('ascii'))
WATERMARK = 'www.eastasiaecon.com'

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
