"""Auto-trade data, loaded ONCE per process.

Parquet read + MultiIndex + per-economy date lookups happen here, not in panel_auto.py
(which Bokeh re-runs per session). ``panel_auto.build_auto_panel()`` reads from this module.

The MultiIndex on (economy, flow, category, iso3) replaces the boolean-masking pattern from
the original region_auto_bokeh main.py — same answers, much faster per click.
"""
import numpy as np
import pandas as pd

from shared_data import HERE

DATA_PARQUET = HERE / 'data' / 'auto_long.parquet'

MEASURE_COL = {'Value (USD bn)': 'value', 'Units': 'units', 'Unit price (USD/car)': 'usd_per_unit'}
UNIT_LABEL = {'Value (USD bn)': 'USD bn', 'Units': 'Units', 'Unit price (USD/car)': 'USD/car'}

_DATA = pd.read_parquet(DATA_PARQUET)
_DATA['Date'] = pd.to_datetime(_DATA['Date'])
CUR = _DATA['Date'].max()

# Each reporter has its own latest month (EU ends one month, UAE another, …); the map must
# colour by the *selected* economy's latest month, not the global max, or it goes blank.
ECON_LAST = _DATA.groupby('economy')['Date'].max()

# MultiIndex on (economy, flow, category, iso3) for O(log n) .loc lookups; matches the
# cn pattern and is much faster than re-masking the 1.6 M-row DataFrame per click.
IDX = (_DATA[['economy', 'flow', 'category', 'iso3', 'Date',
              'value', 'units', 'usd_per_unit']]
       .set_index(['economy', 'flow', 'category', 'iso3']))
if not IDX.index.is_monotonic_increasing:
    IDX = IDX.sort_index()

# Region aggregates (iso3 'R_*', not on the map) — selected via the Region dropdown.
_agg = _DATA[_DATA['iso3'].astype(str).str.startswith('R_')][['country', 'iso3']].drop_duplicates()
REGION_ISO = dict(zip(_agg['country'], _agg['iso3']))
REGION_LABELS = sorted(REGION_ISO)

# Reporters in a sensible order (big four first, then EM/Comtrade reporters).
_PREF_REP = ['Japan', 'Korea', 'China', 'EU', 'India', 'Saudi Arabia', 'UAE',
             'South Africa', 'Russia', 'Russia (reported)']
_reps = set(_DATA['economy'].unique())
REPORTERS = [r for r in _PREF_REP if r in _reps] + sorted(_reps - set(_PREF_REP))

_PREFERRED = ['Total', 'ICE', 'HEV', 'PHEV', 'BEV', 'NEV', 'Hybrid',
              'Hybrid and electric', 'Other', 'Including others']


def _ordered_cats(cats):
    s = set(cats)
    return [c for c in _PREFERRED if c in s] + sorted(c for c in s if c not in _PREFERRED)


CATEGORIES = _ordered_cats(_DATA['category'].unique())
# Powertrains actually available per reporter (Comtrade reporters only have 'Total').
ECON_CATS = {e: _ordered_cats(_DATA.loc[_DATA['economy'] == e, 'category'].unique())
             for e in REPORTERS}

ALL_DATES = [pd.Timestamp(d) for d in np.sort(_DATA['Date'].unique())]

del _DATA, _agg
