"""China-trade data, loaded ONCE per process.

The parquet read, the MultiIndex, and the derived option lists all live here so they
don't repeat per session. ``panel_cn.build_cn_panel()`` reads from this module.
"""
import json
import numpy as np
import pandas as pd

from shared_data import HERE

DATA_PARQUET = HERE / 'data' / 'cn_long.parquet'

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

del _DATA, _agg
