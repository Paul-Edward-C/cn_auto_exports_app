"""China-trade data, loaded ONCE per process.

The parquet read, the MultiIndex, and the derived option lists all live here so they
don't repeat per session. ``panel_cn.build_cn_panel()`` reads from this module.
"""
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from shared_data import HERE

DATA_PARQUET = HERE / 'data' / 'cn_long.parquet'

# self_destruct frees each Arrow buffer as it's converted, so the Arrow + pandas copies
# don't coexist — roughly halves the read transient on a 512 MB dyno.
_DATA = pq.read_table(DATA_PARQUET).to_pandas(split_blocks=True, self_destruct=True)
# Parquet already stores Date as datetime64[ns]; only convert if that ever isn't the case
# (the row-wise to_datetime copy briefly doubles the column — ~70 MB at boot otherwise).
if not np.issubdtype(_DATA['Date'].dtype, np.datetime64):
    _DATA['Date'] = pd.to_datetime(_DATA['Date'])
CUR = _DATA['Date'].max()

# MultiIndex for O(log n) .loc lookups. Built with from_arrays (not set_index) so the index
# shares the columns' categorical arrays instead of copying them — set_index spiked ~+440 MB
# at boot building this same 84 MB index; from_arrays costs ~+55 MB. The parquet is pre-sorted
# by these keys, so the index is monotonic — only sort defensively if that ever isn't the case.
_KEYS = ['flow', 'product', 'product_cat', 'unit', 'iso3']
IDX = pd.DataFrame(
    {'Date': _DATA['Date'].to_numpy(), 'value': _DATA['value'].to_numpy()},
    index=pd.MultiIndex.from_arrays([_DATA[k]._values for k in _KEYS], names=_KEYS),
)
if not IDX.index.is_monotonic_increasing:
    IDX = IDX.sort_index()

# Region aggregates (iso3 'R_*', not on the map) — selected via the Region dropdown.
# iso3 is categorical: test the handful of categories, not all 4.7 M rows. The old
# .astype(str) materialised 4.7 M Python strings — a ~400 MB transient spike at boot.
_r_isos = [c for c in _DATA['iso3'].cat.categories if str(c).startswith('R_')]
_agg = _DATA[_DATA['iso3'].isin(_r_isos)][['country', 'iso3']].drop_duplicates()
REGION_ISO = dict(zip(_agg['country'], _agg['iso3']))
REGION_LABELS = sorted(REGION_ISO)

# Dimension options. Product-category cascades from Product (e.g. Semis has ICs…, Passenger
# cars has ICE…). Auto wording follows the settings/my_functions standard shared with the
# region auto dashboard: product 'Passenger cars', powertrains ICE/HEV/PHEV/BEV/…
_FLOW_ORDER = ['Exports', 'Imports', 'Trade balance']
_PROD_ORDER = ['Total', 'Passenger cars', 'Semis', 'Batteries', 'Solar', 'Rare earths',
               'Industrial robots']
_UNIT_ORDER = ['USD bn', 'USD bn, SA', 'USD mn', 'Unit', 'Unit mn', 'KG mn', 'KG', 'Carat', '-']

# Powertrain ordering mirrors the region auto dashboard's standard (_PREFERRED in its main.py).
_PCAT_ORDER = ['Total', 'ICE', 'HEV', 'PHEV', 'BEV', 'NEV', 'Hybrid',
               'Hybrid and electric', 'Electrified', 'Other']
_CAT_PREF = {'Passenger cars': _PCAT_ORDER}


def _order(values, pref):
    s = set(values)
    return [v for v in pref if v in s] + sorted(v for v in s if v not in pref)


FLOWS = _order(_DATA['flow'].unique(), _FLOW_ORDER)
PRODUCTS = _order(_DATA['product'].unique(), _PROD_ORDER)
UNITS = _order(_DATA['unit'].unique(), _UNIT_ORDER)
PRODUCT_CATS = {p: _order(_DATA.loc[_DATA['product'] == p, 'product_cat'].unique(),
                          _CAT_PREF.get(p, ['Total']))
                for p in PRODUCTS}

ALL_DATES = [pd.Timestamp(d) for d in np.sort(_DATA['Date'].unique())]

del _DATA, _agg
