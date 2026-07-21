"""Build a long, iso3-keyed parquet for cn_auto_bokeh from cn_auto_exports' wide.pkl.

Reporter is always China. Melts each (flow, product, product_cat, unit) date×country frame to
long, maps partner -> iso3, keeps World (iso3 'WLD'), drops the source's own region/aggregate
columns, and synthesises the standard EAE regions (my_functions.REGION_MEMBERS) from member
countries. Also writes region_map.json (iso3 -> primary geographic region) for the app.

    /Users/paul/opt/anaconda3/bin/python build_cn_long.py
"""
import sys
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pycountry

sys.path.insert(0, '/Users/paul/Documents/DATA/settings/final_notebooks')
from my_functions import REGION_MEMBERS

SRC = Path('/Users/paul/Documents/ghost/cn_auto_exports/app/data/optimized/wide.pkl')
# Write straight into app/data/ (the dir the app actually reads) so cn_long.parquet /
# region_map.json don't have to be copied there by hand. This is SRC's parent — keeps the
# output next to the wide.pkl it's built from, regardless of where this script lives.
OUTDIR = SRC.parent.parent
OUTDIR.mkdir(parents=True, exist_ok=True)

REGION_CODE = {
    'Latin America': 'R_LATAM', 'Middle East': 'R_MEA', 'Africa': 'R_AFR',
    'Emerging Europe': 'R_EMEU', 'Emerging Asia ex ASEAN and China': 'R_EMAS',
    'DM ex US and EU': 'R_DM', 'ASEAN': 'R_ASEAN', 'EU': 'R_EU',
    'China and Hong Kong': 'R_CNHK', 'BRI': 'R_BRI', 'EM': 'R_EM',
}

ISO = {
    'US': 'USA', 'UK': 'GBR', 'Korea': 'KOR', 'South Korea': 'KOR', 'North Korea': 'PRK',
    'Russia': 'RUS', 'Vietnam': 'VNM', 'Taiwan': 'TWN', 'Hong Kong': 'HKG', 'Macau': 'MAC',
    'Macao': 'MAC', 'UAE': 'ARE', 'Czech Republic': 'CZE', 'Czechia': 'CZE', 'Turkey': 'TUR',
    'Iran': 'IRN', 'Syria': 'SYR', 'Laos': 'LAO', 'Brunei': 'BRN', 'Moldova': 'MDA',
    'Tanzania': 'TZA', 'Bolivia': 'BOL', 'Venezuela': 'VEN', "Cote d'Ivoire": 'CIV',
    "Côte d'Ivoire": 'CIV', 'Ivory Coast': 'CIV', 'Democratic Republic of the Congo': 'COD',
    'DR Congo': 'COD', 'Republic of the Congo': 'COG', 'Congo': 'COG', 'Cabo Verde': 'CPV',
    'Cape Verde': 'CPV', 'Eswatini': 'SWZ', 'Swaziland': 'SWZ', 'North Macedonia': 'MKD',
    'Macedonia': 'MKD', 'Timor-Leste': 'TLS', 'East Timor': 'TLS', 'Micronesia': 'FSM',
    'Palestine': 'PSE', 'Kosovo': 'XKX', 'Myanmar': 'MMR', 'Burma': 'MMR',
    'St Kitts and Nevis': 'KNA', 'Saint Kitts and Nevis': 'KNA', 'St Lucia': 'LCA',
    'Saint Lucia': 'LCA', 'St Vincent and the Grenadines': 'VCT',
    'Saint Vincent and the Grenadines': 'VCT', 'Sao Tome and Principe': 'STP',
    'Antigua and Barbuda': 'ATG', 'Trinidad and Tobago': 'TTO',
    'Bosnia and Herzegovina': 'BIH', 'Bosnia & Herzegovina': 'BIH',
}


def to_iso3(name):
    if name == 'World':
        return 'WLD'
    n = str(name).replace('&', 'and').strip()
    for key in (name, n):
        if key in ISO:
            return ISO[key]
    for key in (name, n):
        try:
            return pycountry.countries.lookup(key).alpha_3
        except Exception:
            pass
    return None


def main():
    WIDE = pickle.load(open(SRC, 'rb'))['WIDE']
    parts = []
    for (flow, product, pcat, unit), frame in WIDE.items():
        long = frame.reset_index()
        long = long.rename(columns={long.columns[0]: 'Date'})
        long = long.melt(id_vars='Date', var_name='country', value_name='value')
        long = long.dropna(subset=['value'])
        long = long[long['value'] != 0]
        if long.empty:
            continue
        long['flow'], long['product'], long['product_cat'], long['unit'] = flow, product, pcat, unit
        parts.append(long)
    df = pd.concat(parts, ignore_index=True)
    df['Date'] = pd.to_datetime(df['Date'])

    iso_of = {c: to_iso3(c) for c in df['country'].unique()}
    unmapped = sorted(c for c, v in iso_of.items() if v is None)
    df['iso3'] = df['country'].map(iso_of)
    df = df.dropna(subset=['iso3'])     # keeps mappable partners + World (WLD); drops aggregates
    print(f'{len(unmapped)} unmapped partner labels dropped (sample): {unmapped[:15]}')

    # Synthesise the standard regions from member countries (matched on iso3).
    region_iso = {reg: {to_iso3(m) for m in mem} - {None} for reg, mem in REGION_MEMBERS.items()}
    base = df[df['iso3'] != 'WLD']
    reg_frames = []
    for reg, isos in region_iso.items():
        g = base[base['iso3'].isin(isos)]
        if g.empty:
            continue
        w = g.groupby(['flow', 'product', 'product_cat', 'unit', 'Date'],
                      as_index=False)['value'].sum(min_count=1)
        w['country'] = reg
        w['iso3'] = REGION_CODE[reg]
        reg_frames.append(w)
    df = pd.concat([df] + reg_frames, ignore_index=True)

    df = df[['flow', 'product', 'product_cat', 'unit', 'country', 'iso3', 'Date', 'value']]
    # Sort by the app's index keys (iso3, not country) so it can set_index without re-sorting.
    df = df.sort_values(['flow', 'product', 'product_cat', 'unit', 'iso3', 'Date'])
    # Categorical string columns -> ~20x smaller in RAM (parquet stores them dictionary-encoded,
    # so the app loads at ~90 MB instead of ~1.9 GB).
    for c in ['flow', 'product', 'product_cat', 'unit', 'country', 'iso3']:
        df[c] = df[c].astype('category')
    df.to_parquet(OUTDIR / 'cn_long.parquet', engine='pyarrow', compression='snappy', index=False)

    # Country iso3 -> single primary GEOGRAPHIC region (for the app's region highlighting).
    GEO_PRIORITY = ['ASEAN', 'Emerging Asia ex ASEAN and China', 'China and Hong Kong', 'EU',
                    'Emerging Europe', 'Middle East', 'Africa', 'Latin America', 'DM ex US and EU']
    primary = {}
    for reg in GEO_PRIORITY:
        for iso in sorted(region_iso.get(reg, ())):
            primary.setdefault(iso, reg)
    (OUTDIR / 'region_map.json').write_text(json.dumps(primary, ensure_ascii=False))

    print(f'saved cn_long.parquet  {df.shape[0]:,} rows')
    print('flows:', sorted(df['flow'].unique()))
    print('products:', sorted(df['product'].unique()))
    print('units:', sorted(df['unit'].unique()))
    print('World rows:', int((df['iso3'] == 'WLD').sum()),
          '| region rows:', int(df['iso3'].astype(str).str.startswith('R_').sum()))
    print('region_map.json:', len(primary), 'countries')
    print('dates:', df['Date'].min().date(), '->', df['Date'].max().date())


if __name__ == '__main__':
    main()
