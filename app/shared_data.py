"""Process-wide data for the China trade app.

Bokeh re-executes ``main.py`` for EVERY new browser session, so anything done at module
level there (reading the 20 MB parquet, building the 4.7M-row MultiIndex, loading the world
geometry) would repeat on every page load. Everything imported from here, by contrast, runs
ONCE per dyno — Python caches imported modules in ``sys.modules`` — and is shared read-only
across all sessions.

Nothing here is a Bokeh model (those can't be shared between documents); only plain
pandas / list / dict data that callbacks read, never mutate.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA_PARQUET = HERE / 'data' / 'cn_long.parquet'

# ---------------------------------------------------------------- house style
FONT = 'Georgia'
BRAND = '#556B2F'
PANEL_BG = '#f4f9f4'
MAX_SERIES = 4
SERIES_COLORS = ['#4682B4', '#B7410E', '#6B8E23', '#CD5C5C']
CHART_W, CHART_H = 972, 589
_RAMP = ['#87CEEB', '#4682B4', '#FFDB58', '#FFBF00', '#FF7F50', '#B7410E', '#CD5C5C']


def _ramp_palette(stops, n=256):
    """256-stop hex ramp by linear RGB interpolation (avoids importing matplotlib)."""
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in stops], float)
    xs, xi = np.linspace(0, 1, len(stops)), np.linspace(0, 1, n)
    out = np.stack([np.interp(xi, xs, rgb[:, c]) for c in range(3)], axis=1).round().astype(int)
    return ['#%02x%02x%02x' % tuple(c) for c in out]


PALETTE = _ramp_palette(_RAMP)
BACKGROUND_URL = ('https://www.eastasiaecon.com/content/images/size/w2400/2023/04/'
                  'Image-29-4-2023-at-7.34-PM.jpeg')
WATERMARK = 'www.eastasiaecon.com/cn/#charts'

# ---------------------------------------------------------------- data (loaded once)
_DATA = pd.read_parquet(DATA_PARQUET)          # string columns are categorical (~90 MB)
_DATA['Date'] = pd.to_datetime(_DATA['Date'])
CUR = _DATA['Date'].max()
# MultiIndex for O(log n) .loc lookups. The parquet is pre-sorted by these keys, so set_index
# yields a monotonic index — only sort defensively if that ever isn't the case.
IDX = (_DATA[['flow', 'product', 'product_cat', 'unit', 'iso3', 'Date', 'value']]
       .set_index(['flow', 'product', 'product_cat', 'unit', 'iso3']))
if not IDX.index.is_monotonic_increasing:
    IDX = IDX.sort_index()

# Region aggregates (iso3 'R_*', not on the map) — selected via the Region dropdown.
_agg = _DATA[_DATA['iso3'].astype(str).str.startswith('R_')][['country', 'iso3']].drop_duplicates()
REGION_ISO = dict(zip(_agg['country'], _agg['iso3']))
REGION_LABELS = sorted(REGION_ISO)
REGION_OF = json.loads(DATA_PARQUET.parent.joinpath('region_map.json').read_text())  # iso3 -> region

# Dimension options. Product-category cascades from Product (e.g. Semis has ICs…, Autos has ICE…).
_FLOW_ORDER = ['Exports', 'Imports', 'Trade balance']
_PROD_ORDER = ['Total', 'Autos', 'Semis', 'Batteries', 'Solar', 'Rare earths', 'Industrial robots']
_UNIT_ORDER = ['USD bn', 'USD bn, SA', 'USD mn', 'Unit', 'Unit mn', 'KG mn', 'KG', 'Carat', '-']


def _order(values, pref):
    s = set(values)
    return [v for v in pref if v in s] + sorted(v for v in s if v not in pref)


FLOWS = _order(_DATA['flow'].unique(), _FLOW_ORDER)
PRODUCTS = _order(_DATA['product'].unique(), _PROD_ORDER)
UNITS = _order(_DATA['unit'].unique(), _UNIT_ORDER)
PRODUCT_CATS = {p: _order(_DATA.loc[_DATA['product'] == p, 'product_cat'].unique(), ['Total'])
                for p in PRODUCTS}

ALL_DATES = [pd.Timestamp(d) for d in np.sort(_DATA['Date'].unique())]

# World geometry -> plain lists (each session builds its own ColumnDataSource from these).
_WORLD = pd.read_parquet(HERE / 'data' / 'world_patches.parquet')
WORLD_XS = [list(x) for x in _WORLD['xs']]
WORLD_YS = [list(y) for y in _WORLD['ys']]
WORLD_ISO = list(_WORLD['iso3'])
WORLD_NAME = list(_WORLD['name'])
N_PATCH = len(WORLD_ISO)
COUNTRY_NAMES_SORTED = sorted(WORLD_NAME)
ISO_IDX = {iso: j for j, iso in enumerate(WORLD_ISO)}
COUNTRY_ISO = dict(zip(WORLD_NAME, WORLD_ISO))

# Region membership by map patch index (Region dropdown highlights the members).
REGION_MEMBER_IDX = {}
for _j, _iso in enumerate(WORLD_ISO):
    _r = REGION_OF.get(_iso)
    if _r:
        REGION_MEMBER_IDX.setdefault(_r, []).append(_j)

del _DATA, _WORLD, _agg   # only IDX (+ the derived lists) are used at runtime; free the copies
