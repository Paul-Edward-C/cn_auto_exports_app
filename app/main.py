# app/main.py - COMPLETE VERSION with Optimized Data Support
# VERSION: v2.0-COLUMNDATASOURCE-2024-11-15

import json
import re
import difflib
import os
import warnings
from pathlib import Path
from functools import lru_cache
import numpy as np
import pandas as pd
import matplotlib.colors as mcolors

# Heroku detection
IS_HEROKU = os.environ.get('DYNO') is not None
if IS_HEROKU:
    warnings.filterwarnings('ignore', category=DeprecationWarning)

try:
    import geopandas as gpd
except ModuleNotFoundError:
    gpd = None

from bokeh.io import curdoc
from bokeh.models import (
    GeoJSONDataSource, Select, Button, ColumnDataSource, HoverTool, Div, Label,
    NumeralTickFormatter, DatetimeTickFormatter, DataTable, TableColumn,
    HTMLTemplateFormatter, ColorBar, LinearColorMapper, Spacer, DataRange1d,
    InlineStyleSheet, Slider, CustomJS, SaveTool, LinearAxis, Switch, Span, Legend, LegendItem
)
from bokeh.plotting import figure
from bokeh.layouts import column as bokeh_column, row as bokeh_row
from bokeh.themes import Theme

# Use aliases to avoid name conflicts
column = bokeh_column
row = bokeh_row

# Avoid pandas Series name conflict with bokeh
pd_Series = pd.Series

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

WORLD_SHP = DATA_DIR / "ne_10m_admin_0_countries.shp"
WORLD_GEOJSON = DATA_DIR / "ne_10m_admin_0_countries.geojson"
OPTIMIZED_DIR = DATA_DIR / "optimized"

print(f"[BOOT] ===================================")
print(f"[BOOT] VERSION: v2.0-COLUMNDATASOURCE-2024-11-15")
print(f"[BOOT] ===================================")
print(f"[BOOT] Starting initialization...")

# -----------------------------------------------------------------------------
# Check for Optimized Data
# -----------------------------------------------------------------------------
USE_OPTIMIZED = (
    OPTIMIZED_DIR.exists() and 
    (OPTIMIZED_DIR / "data_normalized.parquet").exists() and
    (OPTIMIZED_DIR / "column_metadata.parquet").exists() and
    (OPTIMIZED_DIR / "dates.parquet").exists()
)

if USE_OPTIMIZED:
    print("[BOOT] ✅ Using OPTIMIZED data structure")
else:
    print("[BOOT] ℹ️  Using ORIGINAL data structure")
    print("[BOOT] 💡 Run restructure_data_simple.ipynb for 100x speed improvement!")

# -----------------------------------------------------------------------------
# World Geometry
# -----------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_world_geometry():
    """Load and cache world geometry"""
    print("[CACHE] Loading world geometry...")
    world = None
    _using_gpd = False
    
    try:
        if WORLD_GEOJSON.exists():
            with WORLD_GEOJSON.open('r', encoding='utf-8') as f:
                gj = json.load(f)
            world = pd.DataFrame([feat["properties"] | {"__geom": feat["geometry"]} for feat in gj["features"]])
            _using_gpd = False
        elif gpd is not None and WORLD_SHP.exists():
            world = gpd.read_file(WORLD_SHP.as_posix())
            _using_gpd = True
        else:
            raise FileNotFoundError("No world shapefile/geojson found")
    except Exception as e:
        if WORLD_GEOJSON.exists():
            with WORLD_GEOJSON.open('r', encoding='utf-8') as f:
                gj = json.load(f)
            world = pd.DataFrame([feat["properties"] | {"__geom": feat["geometry"]} for feat in gj["features"]])
            _using_gpd = False
        else:
            raise RuntimeError(f"Failed to load world geometry: {e}")
    
    if not _using_gpd and 'geometry' not in world.columns and '__geom' in world.columns:
        world = world.rename(columns={'__geom': 'geometry'})
    
    print(f"[CACHE] World geometry loaded: {len(world)} features")
    return world, _using_gpd

world, _using_gpd = load_world_geometry()

# -----------------------------------------------------------------------------
# Data Loading - OPTIMIZED or ORIGINAL
# -----------------------------------------------------------------------------

if USE_OPTIMIZED:
    # OPTIMIZED MODE - Load only metadata, query data on-demand
    
    @lru_cache(maxsize=1)
    def load_metadata():
        print("[CACHE] Loading metadata...")
        meta = pd.read_parquet(OPTIMIZED_DIR / "column_metadata.parquet")
        print(f"[CACHE] Metadata loaded: {len(meta)} columns")
        return meta
    
    @lru_cache(maxsize=1)
    def load_dates():
        print("[CACHE] Loading dates...")
        dates = pd.read_parquet(OPTIMIZED_DIR / "dates.parquet")
        dates['date'] = pd.to_datetime(dates['date'])
        print(f"[CACHE] Dates loaded: {len(dates)} dates")
        return dates
    
    metadata_df = load_metadata()
    dates_df = load_dates()
    
    # Build schema from metadata
    flows = set(metadata_df['flow'].unique())
    countries = set(metadata_df['country'].unique())
    products = set(metadata_df['product'].unique())
    product_cats = set(metadata_df['product_cat'].unique())
    types_set = set(metadata_df['unit'].unique())
    
    DATE_LIST = dates_df['date'].dt.to_pydatetime().tolist()
    DATE_LABELS = [pd.Timestamp(d).strftime("%b %Y") for d in DATE_LIST]
    DATE_ROW_IDXS = list(range(len(DATE_LIST)))
    date_col = 'date'
    
    # Key to column mapping
    key_to_col = {}
    for _, data_row in metadata_df.iterrows():
        key = (data_row['flow'], data_row['country'], data_row['product'], data_row['product_cat'], data_row['unit'])
        key_to_col[key] = data_row['column']
    
    # On-demand data loading
    @lru_cache(maxsize=100)
    def get_data_for_series(flow, country, product, product_cat, unit):
        """Load specific time series on-demand"""
        filters = [
            ('flow', '=', flow),
            ('country', '=', country),
            ('product', '=', product),
            ('product_cat', '=', product_cat),
            ('unit', '=', unit)
        ]
        try:
            data = pd.read_parquet(
                OPTIMIZED_DIR / "data_normalized.parquet",
                filters=filters,
                columns=['date', 'value']
            )
            # Create series aligned with DATE_LIST
            result = pd_Series(index=pd.DatetimeIndex(DATE_LIST), dtype=float)
            for _, data_row in data.iterrows():
                if pd.Timestamp(data_row['date']) in result.index:
                    result[pd.Timestamp(data_row['date'])] = data_row['value']
            return result
        except:
            return pd.Series([np.nan] * len(DATE_LIST), index=pd.DatetimeIndex(DATE_LIST))
    
    @lru_cache(maxsize=100)
    def get_snapshot_for_date(flow, product, product_cat, unit, date_idx):
        """Load all countries for specific combo and date"""
        if date_idx >= len(DATE_LIST):
            return {}
        
        target_date = DATE_LIST[date_idx]
        filters = [
            ('flow', '=', flow),
            ('product', '=', product),
            ('product_cat', '=', product_cat),
            ('unit', '=', unit)
        ]
        try:
            data = pd.read_parquet(
                OPTIMIZED_DIR / "data_normalized.parquet",
                filters=filters,
                columns=['date', 'country', 'value']
            )
            # Find closest date
            data['date'] = pd.to_datetime(data['date'])
            date_mask = (data['date'] >= target_date) & (data['date'] < target_date + pd.Timedelta(days=32))
            snapshot = data[date_mask].groupby('country')['value'].last()
            return snapshot.to_dict()
        except Exception as e:
            print(f"[ERROR] Snapshot load: {e}")
            return {}
    
    print(f"[BOOT] Schema: {len(flows)} flows, {len(countries)} countries, {len(products)} products")

else:
    # ORIGINAL MODE - Load full parquet with caching
    
    DF_PATH = DATA_DIR / "auto_total.parquet"
    
    def _normalize_header(s: str) -> str:
        s = (s or "").replace("\ufeff", "").replace("\xa0", " ")
        parts = [p.strip() for p in s.split(",")]
        return ", ".join(parts)
    
    @lru_cache(maxsize=1)
    def load_main_data():
        print("[CACHE] Loading parquet data...")
        start_time = pd.Timestamp.now()
        
        if not DF_PATH.exists():
            raise FileNotFoundError(f"Data file not found: {DF_PATH}")
        
        df = pd.read_parquet(DF_PATH.as_posix(), engine='pyarrow')
        df = df.reset_index()
        df.columns = [_normalize_header(c) for c in df.columns]
        
        elapsed = (pd.Timestamp.now() - start_time).total_seconds()
        print(f"[CACHE] Parquet loaded in {elapsed:.2f}s: {df.shape[0]} rows × {df.shape[1]} cols")
        return df
    
    df = load_main_data()
    
    date_col = next((c for c in df.columns if re.search(r'date', c, re.IGNORECASE)), None)
    if not date_col:
        raise RuntimeError("No 'date' column found")
    
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df = df.sort_values(date_col).reset_index(drop=True)
    
    _norm_all = df[date_col].dropna().dt.normalize()
    _date_uni = _norm_all.drop_duplicates().sort_values()
    DATE_LIST = [d.to_pydatetime() for d in _date_uni]
    DATE_LABELS = [pd.Timestamp(d).strftime("%b %Y") for d in DATE_LIST]
    _last_idx = _norm_all.groupby(_norm_all).apply(lambda s: s.index[-1])
    DATE_ROW_IDXS = [int(_last_idx.loc[pd.Timestamp(d)]) for d in _date_uni]
    
    # Parse schema
    @lru_cache(maxsize=1)
    def parse_and_cache_schema():
        print("[CACHE] Parsing schema...")
        key_to_col = {}
        flows, countries, products, product_cats, types_set = set(), set(), set(), set(), set()
        
        def parse_schema(colname: str):
            parts = [p.strip() for p in colname.split(",")]
            if len(parts) >= 6 and parts[0].lower() == "china":
                flow, country, product, product_cat = parts[1], parts[2], parts[3], parts[4]
                unit = ", ".join(parts[5:]).strip()
                return (flow, country, product, product_cat, unit)
            return None
        
        for col in df.columns:
            parsed = parse_schema(col)
            if parsed is None:
                continue
            flow, country, product, product_cat, unit = parsed
            key_to_col[(flow, country, product, product_cat, unit)] = col
            flows.add(flow)
            countries.add(country)
            products.add(product)
            product_cats.add(product_cat)
            types_set.add(unit)
        
        print(f"[CACHE] Schema parsed: {len(key_to_col)} columns indexed")
        return key_to_col, flows, countries, products, product_cats, types_set
    
    key_to_col, flows, countries, products, product_cats, types_set = parse_and_cache_schema()
    
    # Clean numeric columns
    print("[BOOT] Converting numeric columns...")
    for col in set(key_to_col.values()) & set(df.columns):
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(',', '', regex=False)
                  .str.replace('\u202f', '', regex=False)
                  .str.replace('\xa0', '', regex=False).str.strip(),
            errors='coerce'
        )
    
    # Original data access functions
    def get_data_for_series(flow, country, product, product_cat, unit):
        col = key_to_col.get((flow, country, product, product_cat, unit))
        if not col or col not in df.columns:
            return pd.Series([np.nan] * len(DATE_LIST), index=pd.DatetimeIndex(DATE_LIST))
        return pd.Series(df[col].values, index=pd.DatetimeIndex(DATE_LIST))
    
    def get_snapshot_for_date(flow, product, product_cat, unit, date_idx):
        if date_idx >= len(DATE_ROW_IDXS):
            return {}
        row_idx = DATE_ROW_IDXS[date_idx]
        data_row = df.iloc[row_idx]
        result = {}
        for country in countries:
            col = key_to_col.get((flow, country, product, product_cat, unit))
            if col and col in df.columns:
                try:
                    result[country] = float(data_row[col])
                except:
                    pass
        return result

# -----------------------------------------------------------------------------
# Common helpers
# -----------------------------------------------------------------------------

def _geom_bounds_list(geom):
    t = geom.get("type")
    coords = geom.get("coordinates", [])
    xs, ys = [], []
    if t == "Polygon":
        for ring in coords:
            for x, y in ring:
                xs.append(x); ys.append(y)
    elif t == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for x, y in ring:
                    xs.append(x); ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs and ys else (0, 0, 1, 1)

def _total_bounds_df(df_like):
    xmins, ymins, xmaxs, ymaxs = [], [], [], []
    for g in df_like["geometry"]:
        xmin, ymin, xmax, ymax = _geom_bounds_list(g)
        xmins.append(xmin); ymins.append(ymin); xmaxs.append(xmax); ymaxs.append(ymax)
    return (min(xmins), min(ymins), max(xmaxs), max(ymaxs)) if xmins else (0, 0, 1, 1)

# Theme - Match your other workflow settings (without toolbar override)
theme_json = {
    'attrs': {
        'figure': {
            'width': 972,
            'height': 589,
            # Removed 'toolbar_location': None - let each figure control its own toolbar
            'background_fill_color': '#228B22', 
            'background_fill_alpha': 0.05
        },
        'Axis': {'axis_label_text_font': 'Georgia', 'major_label_text_font': 'Georgia'},
        'Title': {'text_font_style': 'bold', 'text_font': 'Georgia', 'text_font_size': '18px'},
        'Legend': {'label_text_font': 'Georgia', 'padding': 1, 'spacing': 1, 'background_fill_alpha': 0.7},
        "Label": {
            "text_font": "Georgia", "text_font_size": "0.875em", "text_font_style": "bold",
            "text_color": "#556B2F", "text_align": "left", "text_baseline": "bottom",
            "background_fill_alpha": 1.0, "border_line_alpha": 0.3, "border_line_width": 0.5,
            "border_line_color": "#A9A9A9", "padding": 5
        }
    }
}
curdoc().theme = Theme(json=theme_json)

# Palette
color_map = {
    'c1': '#556B2F', 'c2': '#B7410E', 'c3': '#4682B4', 'c4': '#FF7F50',
    'c5': '#228B22', 'c6': '#FFBF00', 'c7': '#87CEEB', 'c8': '#FFDB58',
    'c9': '#6B8E23', 'c10': '#CD5C5C'
}
custom_palette = [color_map['c7'], color_map['c3'], color_map['c8'],
                  color_map['c6'], color_map['c4'], color_map['c2'], color_map['c10']]

@lru_cache(maxsize=10)
def interpolate_palette(palette_tuple, n):
    palette = list(palette_tuple)
    cmap = mcolors.LinearSegmentedColormap.from_list('custom', palette)
    return [mcolors.to_hex(cmap(i/(n-1))) for i in range(n)]

smooth_palette = interpolate_palette(tuple(custom_palette), 50)

formatter = HTMLTemplateFormatter(template="""
<style>
  .slick-column-name {font-family: Georgia; font-weight: 900; font-size: 0.9rem;}
  .slick-header-column {background-color: hsla(120, 100%, 25%, 0.1) !important;}
  .slick-cell {font-family: Georgia; font-size: 0.9rem;}
  .slick-row:nth-of-type(even) {background-color: hsla(120, 100%, 25%, 0.1) !important;}
</style>
<%= (value != null) ? value.toFixed(2) : "N/A" %>
""")

def latest_date_label(fmt="%b %Y"):
    return pd.Timestamp(DATE_LIST[-1]).strftime(fmt) if DATE_LIST else "Latest"

def pick_default(options, preferred=None):
    if preferred and preferred in options:
        return preferred
    return sorted(list(options))[0] if options else None

default_flow = pick_default(flows, 'Exports')
default_product = pick_default(products, 'Total')
default_product_cat = pick_default(product_cats, 'Total')
default_type = pick_default(types_set, 'USD bn')

# Country matching
@lru_cache(maxsize=1)
def build_filtered_world():
    print("[CACHE] Building filtered world...")
    country_list = sorted([c for c in countries if c != 'World'])
    
    def has_match(admin_name):
        match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
        return bool(match)
    
    filtered = world[world['ADMIN'].apply(has_match)].copy().reset_index(drop=True)
    if 'geometry' not in filtered.columns and '__geom' in filtered.columns:
        filtered = filtered.rename(columns={'__geom': 'geometry'})
    
    admin_to_df_map = {}
    for admin_name in filtered['ADMIN']:
        match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
        admin_to_df_map[admin_name] = match[0] if match else None
    
    if not (filtered["ADMIN"] == "China").any():
        china_row = world[world["ADMIN"] == "China"]
        if not china_row.empty:
            china_row = china_row.copy()
            if 'geometry' not in china_row.columns and '__geom' in china_row.columns:
                china_row = china_row.rename(columns={'__geom': 'geometry'})
            filtered = pd.concat([filtered, china_row], ignore_index=True)
    
    terms_dict = {
        "United States of America": "US",
        "United Arab Emirates": "UAE",
        "United Kingdom": "UK",
        "Hong Kong S.A.R": 'Hong Kong'
    }
    filtered["ADMIN_DISPLAY"] = filtered["ADMIN"].replace(terms_dict)
    
    print(f"[CACHE] Filtered world built: {len(filtered)} countries")
    return filtered, admin_to_df_map

filtered_world, admin_to_df_map = build_filtered_world()

# Helper functions
def available_countries_for_combo(flow, product, product_cat, type_str):
    if USE_OPTIMIZED:
        mask = (
            (metadata_df['flow'] == flow) &
            (metadata_df['product'] == product) &
            (metadata_df['product_cat'] == product_cat) &
            (metadata_df['unit'] == type_str)
        )
        return metadata_df[mask]['country'].unique().tolist()
    else:
        return [c for c in countries if (flow, c, product, product_cat, type_str) in key_to_col]

def is_world_only(flow, product, product_cat, type_str):
    cs = available_countries_for_combo(flow, product, product_cat, type_str)
    return len([c for c in cs if c != 'World']) == 0

def is_currency_type(type_str):
    return bool(re.search(r'\b(USD|CNY)\b', type_str)) and bool(re.search(r'\b(bn|m)\b', type_str))

def should_log(flow, type_str):
    return flow != 'Balance' and is_currency_type(type_str)

def has_sa_data(flow, country, product, product_cat, unit):
    """Check if seasonally adjusted data exists for this combination"""
    sa_unit = f"{unit}, SA"
    if USE_OPTIMIZED:
        mask = (
            (metadata_df['flow'] == flow) &
            (metadata_df['country'] == country) &
            (metadata_df['product'] == product) &
            (metadata_df['product_cat'] == product_cat) &
            (metadata_df['unit'] == sa_unit)
        )
        return mask.any()
    else:
        return (flow, country, product, product_cat, sa_unit) in key_to_col

def world_to_geojson(df_like):
    cols = ['ADMIN', 'ADMIN_DISPLAY', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    df_like = df_like[cols]
    if _using_gpd:
        return df_like.to_json()
    feats = []
    for _, r in df_like.iterrows():
        props = {k: (None if pd.isna(r.get(k)) else r.get(k)) 
                 for k in ['ADMIN', 'ADMIN_DISPLAY', 'exports', 'exports_log', 'note', 'custom_color']}
        feats.append({"type": "Feature", "properties": props, "geometry": r["geometry"]})
    return json.dumps({"type": "FeatureCollection", "features": feats})

def get_colors(export_values, palette, vmin, vmax, highlight_admins=None):
    arr = np.asarray(export_values, dtype=float)
    mask = np.isfinite(arr)
    n = len(palette)
    idx = np.zeros_like(arr, dtype=int)
    if vmax > vmin:
        norm = (arr[mask] - vmin) / (vmax - vmin)
        norm = np.clip(norm, 0.0, 1.0)
        idx[mask] = np.round(norm * (n - 1)).astype(int)
    colors = []
    admins = filtered_world["ADMIN"].tolist()
    for k, admin in enumerate(admins):
        if not mask[k]:
            colors.append("#dddddd")
        elif highlight_admins is not None and admin not in highlight_admins:
            colors.append("#dddddd")
        else:
            colors.append(palette[int(idx[k])])
    return colors

def _scale_values_for_map(flow, type_str):
    vals = pd.to_numeric(filtered_world["exports"], errors="coerce")
    if should_log(flow, type_str):
        try:
            minv = float(np.nanmin(vals.values))
        except:
            minv = np.nan
        if np.isfinite(minv) and minv >= 0:
            return vals.apply(lambda x: np.log1p(x) if pd.notnull(x) else np.nan).astype(float)
    return vals.astype(float)

# Widgets
s_flow = Select(title="Flow", value=default_flow, options=sorted(list(flows)), width=160)
s_product = Select(title="Product", value=default_product, options=sorted(list(products)), width=180)
s_product_cat = Select(title="Category", value=default_product_cat, options=sorted(list(product_cats)), width=200)
s_type = Select(title="Unit", value=default_type, options=sorted(list(types_set)), width=140)

def cur_snap():
    return (s_flow.value, s_product.value, s_product_cat.value, s_type.value)

x_flow = Select(title="Flow", value=default_flow, options=sorted(list(flows)), width=160)
x_product = Select(title="Product", value=default_product, options=sorted(list(products)), width=180)
x_product_cat = Select(title="Category", value=default_product_cat, options=sorted(list(product_cats)), width=200)
x_type = Select(title="Unit", value=default_type, options=sorted(list(types_set)), width=140)
x_country_sel = Select(title="Country", value="World", options=["World"], width=220)

# SA toggle for series section
x_sa_toggle = Switch(active=False, width=40)
x_sa_label = Div(text="SA", width=30, styles={
    "font-family": "Georgia, serif",
    "font-size": "14px",
    "font-weight": "bold",
    "color": "#556B2F",
    "padding-top": "6px"
})

def cur_series():
    return (x_flow.value, x_country_sel.value, x_product.value, x_product_cat.value, x_type.value)

month_slider = Slider(title="", start=0, end=max(len(DATE_LIST)-1, 0),
                      value=max(len(DATE_LIST)-1, 0), step=1, width=500)

play_button = Button(label="► Play", width=70)
pause_button = Button(label="❚❚ Pause", width=90, disabled=True)

app_footnote = Div(
    text="Source: EAE, CCA",
    width=972,  # Match figure width
    styles={
        "font-family": "Georgia, serif",
        "font-size": "12px",
        "color": "#333",
        "text-align": "right",
        "border-top": "1px solid #104b1f",
        "margin-top": "8px",
        "padding-top": "6px",
    },
)

# Data sources
filtered_world["exports"] = np.nan
filtered_world["exports_log"] = np.nan
filtered_world["note"] = ""
filtered_world["custom_color"] = "#dddddd"
columns_to_keep = ['ADMIN', 'ADMIN_DISPLAY', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']

# OPTIMIZATION: Convert to ColumnDataSource with static geometry
# Build xs, ys arrays once from geometry
print("[OPTIMIZE] Converting geometry to patches...")
patches_data = {
    'xs': [],
    'ys': [],
    'ADMIN': [],
    'ADMIN_DISPLAY': [],
    'exports': [],
    'exports_log': [],
    'note': [],
    'custom_color': []
}

for idx, geo_row in filtered_world.iterrows():
    geom = geo_row['geometry']
    admin = geo_row['ADMIN']
    admin_display = geo_row['ADMIN_DISPLAY']
    
    # Extract coordinates from geometry
    if isinstance(geom, dict):
        coords = geom.get('coordinates', [])
        geom_type = geom.get('type', '')
        
        if geom_type == 'Polygon':
            for ring in coords:
                xs = [c[0] for c in ring]
                ys = [c[1] for c in ring]
                patches_data['xs'].append(xs)
                patches_data['ys'].append(ys)
                patches_data['ADMIN'].append(admin)
                patches_data['ADMIN_DISPLAY'].append(admin_display)
                patches_data['exports'].append(None)  # Use None instead of np.nan
                patches_data['exports_log'].append(None)
                patches_data['note'].append("")
                patches_data['custom_color'].append("#dddddd")
        
        elif geom_type == 'MultiPolygon':
            for polygon in coords:
                for ring in polygon:
                    xs = [c[0] for c in ring]
                    ys = [c[1] for c in ring]
                    patches_data['xs'].append(xs)
                    patches_data['ys'].append(ys)
                    patches_data['ADMIN'].append(admin)
                    patches_data['ADMIN_DISPLAY'].append(admin_display)
                    patches_data['exports'].append(None)  # Use None instead of np.nan
                    patches_data['exports_log'].append(None)
                    patches_data['note'].append("")
                    patches_data['custom_color'].append("#dddddd")
    
    elif _using_gpd and hasattr(geom, 'geom_type'):
        if geom.geom_type == 'Polygon':
            xs, ys = geom.exterior.xy
            patches_data['xs'].append(list(xs))
            patches_data['ys'].append(list(ys))
            patches_data['ADMIN'].append(admin)
            patches_data['ADMIN_DISPLAY'].append(admin_display)
            patches_data['exports'].append(None)  # Use None instead of np.nan
            patches_data['exports_log'].append(None)
            patches_data['note'].append("")
            patches_data['custom_color'].append("#dddddd")
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                xs, ys = poly.exterior.xy
                patches_data['xs'].append(list(xs))
                patches_data['ys'].append(list(ys))
                patches_data['ADMIN'].append(admin)
                patches_data['ADMIN_DISPLAY'].append(admin_display)
                patches_data['exports'].append(None)  # Use None instead of np.nan
                patches_data['exports_log'].append(None)
                patches_data['note'].append("")
                patches_data['custom_color'].append("#dddddd")

print(f"[OPTIMIZE] Created {len(patches_data['xs'])} patches from {len(filtered_world)} countries")

# CRITICAL: Validate data - no None/null values allowed in xs/ys
print("[OPTIMIZE] Validating patch data...")
for i, (xs, ys) in enumerate(zip(patches_data['xs'], patches_data['ys'])):
    if xs is None or ys is None or len(xs) == 0 or len(ys) == 0:
        print(f"[ERROR] Invalid patch at index {i}: xs={xs}, ys={ys}")
    # Convert any numpy arrays to plain lists
    if hasattr(xs, 'tolist'):
        patches_data['xs'][i] = xs.tolist()
    if hasattr(ys, 'tolist'):
        patches_data['ys'][i] = ys.tolist()

# Ensure exports/exports_log use None instead of np.nan for JS compatibility
# Other fields should have appropriate defaults
for i in range(len(patches_data['ADMIN'])):
    if patches_data['exports'][i] is not None and np.isnan(patches_data['exports'][i]):
        patches_data['exports'][i] = None
    if patches_data['exports_log'][i] is not None and np.isnan(patches_data['exports_log'][i]):
        patches_data['exports_log'][i] = None

print(f"[OPTIMIZE] Validation complete. Sample patch: {len(patches_data['xs'][0])} points")

# Use ColumnDataSource instead of GeoJSONDataSource
geo_source = ColumnDataSource(patches_data)

# Keep a mapping of admin name to patch indices for fast updates
admin_to_patch_idx = {}
for i, admin in enumerate(patches_data['ADMIN']):
    if admin not in admin_to_patch_idx:
        admin_to_patch_idx[admin] = []
    admin_to_patch_idx[admin].append(i)

top15_table_source = ColumnDataSource(data=dict(country=[], value=[]))
top15_chart_source = ColumnDataSource(data=dict(country=[], value=[]))

series_source = ColumnDataSource(data=dict(date=[], value=[]))
series_table_source = ColumnDataSource(data=dict(index=[], date=[], value=[]))

# Multi-series support
SERIES_COLORS = ['#556B2F', '#B7410E', '#4682B4', '#FF7F50', '#8B008B', '#008B8B', '#DAA520', '#2F4F4F']
multi_series_data = []  # List of {source, renderer, label, key}
multi_series_legend_items = []

# Figures
# Create custom save tool with explicit export dimensions
save_tool = SaveTool()
TOOLS = ["pan", "wheel_zoom", "box_zoom", "reset", "hover", save_tool]
latest_label = latest_date_label()

p = figure(
    title=f"China, {default_flow}, {default_product}, {default_product_cat}, {default_type}, {latest_label}",
    tools=TOOLS, x_axis_location=None, y_axis_location=None,
    active_scroll='wheel_zoom', 
    width=972, height=589,  # Match theme settings from other workflow
    toolbar_location="right",  # Override theme's null toolbar
    output_backend="webgl"
)
p.grid.grid_line_color = None

# Apply same title formatting as series chart
p.title.text_font_style = "bold"
p.title.text_font = "Georgia"
p.title.text_font_size = "25px"

if _using_gpd:
    xmin, ymin, xmax, ymax = filtered_world.total_bounds
else:
    xmin, ymin, xmax, ymax = _total_bounds_df(filtered_world)

p.x_range.start, p.x_range.end = float(xmin), float(xmax)
p.y_range.start, p.y_range.end = float(ymin), float(ymax)

color_mapper_obj = LinearColorMapper(palette=smooth_palette, low=0.0, high=1.0, nan_color="#dddddd")
color_bar = ColorBar(color_mapper=color_mapper_obj, label_standoff=12, location=(0, 0),
                     title=f"{default_flow}, {default_product}, {default_product_cat}")
p.add_layout(color_bar, 'right')
p.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text="www.eastasiaecon.com/cn/#charts"))

# Create patches - use simple string reference for fill_color
patches = p.patches(
    xs='xs', 
    ys='ys', 
    source=geo_source, 
    fill_color='custom_color',  # Simple string reference
    fill_alpha=0.7, 
    line_color="gray", 
    line_width=0.5
)

hover = p.select_one(HoverTool)
hover.point_policy = "follow_mouse"
hover.tooltips = [
    ("Country", "@ADMIN_DISPLAY"), 
    ("Value", "@exports{0,0.00}"),  # Will show NaN for None values
    ("Note", "@note")
]
# Make hover more forgiving of None values
hover.attachment = "horizontal"

BACKGROUND_URL = "https://www.eastasiaecon.com/content/images/size/w2400/2023/04/Image-29-4-2023-at-7.34-PM.jpeg"
bg_map_src = ColumnDataSource(dict(url=[BACKGROUND_URL],
                                   x=[p.x_range.start], y=[p.y_range.start],
                                   w=[p.x_range.end - p.x_range.start], h=[p.y_range.end - p.y_range.start]))
p.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_map_src,
            anchor="bottom_left", global_alpha=0.18, level="underlay")

# Top 15 bar
top15_chart = figure(
    x_range=[], height=350, width=370,
    title=f"{default_flow}, {default_product}, {default_product_cat}, {default_type}, {latest_label}",
    toolbar_location=None, tools="", min_border_left=10, min_border_right=10, min_border_top=10, min_border_bottom=10
)
top15_chart.vbar(x="country", top="value", source=top15_chart_source, width=0.7, color="#556B2F", alpha=0.7)
top15_chart.xaxis.major_label_orientation = 1.0
top15_chart.xgrid.grid_line_color = None
top15_chart.title.text_font_size = "14px"

# Series line chart
series_xr = DataRange1d(only_visible=True, range_padding=0.02)
series_yr = DataRange1d(only_visible=True, range_padding=0.08)

# Create custom save tool for series chart
series_save_tool = SaveTool()

series_chart = figure(
    height=589, width=972, title="Series",
    x_axis_type="datetime",
    x_range=series_xr, y_range=series_yr,
    tools=["pan", "xwheel_zoom", "box_zoom", "reset", series_save_tool],
    toolbar_location="right",
    margin=(20, 10, 10, 10)
)

# Primary line shows current selection (always visible as preview)
line_ts = series_chart.line(x="date", y="value", source=series_source, line_width=3, color='#556B2F', alpha=0.8)
series_xr.renderers = [line_ts]
series_yr.renderers = [line_ts]

# Horizontal span at zero
zero_span = Span(location=0, dimension='width', line_color='#999999', line_dash='solid', line_width=1)
series_chart.add_layout(zero_span)

# Legend for multi-series (initially empty, inside chart)
series_legend = Legend(items=[], location="top_left", click_policy="hide",
                       label_text_font="Georgia", label_text_font_size="12px",
                       background_fill_alpha=0.7, background_fill_color="white",
                       border_line_color="#556B2F", border_line_alpha=0.5)
series_chart.add_layout(series_legend)

# Add right y-axis (mirroring the left axis)
right_axis = LinearAxis(y_range_name="default")
right_axis.formatter = NumeralTickFormatter(format="0,0.0")
series_chart.add_layout(right_axis, 'right')

# Apply custom formatting from your workflow
# Left Y-axis
series_chart.yaxis.formatter = NumeralTickFormatter(format="0,0.0")
series_chart.yaxis.axis_label_text_font = "Georgia"
series_chart.yaxis.axis_label_text_font_size = "18px"
series_chart.yaxis.major_label_text_font = "Georgia"
series_chart.yaxis.major_label_text_font_size = "20px"

# Right Y-axis (already has formatter from above)
right_axis.axis_label_text_font = "Georgia"
right_axis.axis_label_text_font_size = "18px"
right_axis.major_label_text_font = "Georgia"
right_axis.major_label_text_font_size = "20px"

# X-axis
series_chart.xaxis.formatter = DatetimeTickFormatter(months="%b %Y")
series_chart.xaxis.axis_label_text_font = "Georgia"
series_chart.xaxis.axis_label_text_font_size = "18px"
series_chart.xaxis.major_label_text_font = "Georgia"
series_chart.xaxis.major_label_text_font_size = "20px"

# Title
series_chart.title.text_font_style = "bold"
series_chart.title.text_font = "Georgia"
series_chart.title.text_font_size = "25px"

hover_ts = HoverTool(
    tooltips=[("Date", "@date{%b %Y}"), ("Value", "@value{0,0.0}")],
    formatters={"@date": "datetime"},
    mode="vline"
)
series_chart.add_tools(hover_ts)
series_chart.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text="www.eastasiaecon.com/cn/#charts"))

bg_series_src = ColumnDataSource(dict(url=[BACKGROUND_URL], x=[0], y=[0], w=[1], h=[1]))
series_chart.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_series_src,
                       anchor="bottom_left", global_alpha=0.12, level="underlay")

# Tables & Buttons
date_width = 200
val_width = 150
series_columns = [
    TableColumn(field="date", title="Date", width=date_width),
    TableColumn(field="value", title="Value", formatter=formatter, width=val_width),
]
series_table = DataTable(
    source=series_table_source,
    columns=series_columns,
    width=500,  # Wider to accommodate multiple series
    height=320,
    index_position=None,
    header_row=True
)

top15_button = Button(label="Highlight Top 15", button_type="success", width=220, height=35)
reset_button = Button(label="🔄", button_type="default", width=40, height=35)
download_series_button = Button(label="Download Series CSV", button_type="primary", width=220, height=35)
download_top15_button = Button(label="Download Top 15 CSV", button_type="primary", width=220, height=35)

# Multi-series buttons
add_series_button = Button(label="+ Add Series", button_type="success", width=120, height=35)
clear_series_button = Button(label="Clear All", button_type="warning", width=100, height=35)

BTN_CSS = """
:host .bk-btn { font-size: 0.9rem; font-family: Georgia, serif; border: none; border-radius: 5px;
  background: #104b1f; color: white; height: 35px; width: 220px; margin: 0; padding: 0 10px; box-shadow: none; }
"""
RESET_CSS = """
:host .bk-btn { font-size: 0.9rem; font-family: Georgia, serif; border: none; border-radius: 5px;
  background: #104b1f; color: white; height: 35px; width: 40px; margin: 0; padding: 0 6px; box-shadow: none; }
"""
SELECTS_CSS = """
:host .bk-input-group{
    font-size: 1.1rem;
    font-family: Georgia, serif;
    font-weight: 900;
    color: black;
}
:host .bk-input{
    font-size: 0.9rem;
    font-family: Georgia, serif;
    background-color: hsla(120,100%,25%,0.1);
    color: black;
}
:host .choices__item.solid.choices__item--selectable{
    font-size: 0.9rem;
    font-family: Georgia, serif;
    background: #104b1f;
}
"""
SWITCH_CSS = """
:host .bk-switch {
    width: 40px;
    height: 20px;
}
:host .bk-switch .bk-knob {
    background-color: #999999;
}
:host .bk-switch input:checked + .bk-knob {
    background-color: #556B2F;
}
:host .bk-switch .bk-bar {
    background-color: hsla(120, 100%, 25%, 0.2);
}
:host .bk-switch input:checked + .bk-knob + .bk-bar {
    background-color: hsla(120, 100%, 25%, 0.3);
}
"""
btn_sheet = InlineStyleSheet(css=BTN_CSS)
reset_sheet = InlineStyleSheet(css=RESET_CSS)
selects_sheet = InlineStyleSheet(css=SELECTS_CSS)
switch_sheet = InlineStyleSheet(css=SWITCH_CSS)

for b in (top15_button, download_top15_button, download_series_button):
    b.stylesheets = [btn_sheet]
reset_button.stylesheets = [reset_sheet]

# Style for smaller buttons
SMALL_BTN_CSS = """
:host .bk-btn { font-size: 0.85rem; font-family: Georgia, serif; border: none; border-radius: 5px;
  background: #104b1f; color: white; height: 35px; margin: 0; padding: 0 10px; box-shadow: none; }
"""
small_btn_sheet = InlineStyleSheet(css=SMALL_BTN_CSS)
add_series_button.stylesheets = [small_btn_sheet]
clear_series_button.stylesheets = [small_btn_sheet]

for w in (s_flow, s_product, s_product_cat, s_type,
          x_flow, x_product, x_product_cat, x_type, x_country_sel):
    w.stylesheets = [selects_sheet]

x_sa_toggle.stylesheets = [switch_sheet]

for b in (top15_button, download_top15_button, download_series_button):
    b.css_classes = ["styled-btn"]
reset_button.css_classes = ["icon-btn"]

# Category options
def available_categories_for_combo(flow, product, type_str=None):
    if USE_OPTIMIZED:
        mask = (metadata_df['flow'] == flow) & (metadata_df['product'] == product)
        if type_str:
            mask = mask & (metadata_df['unit'] == type_str)
        cats = metadata_df[mask]['product_cat'].unique()
        return sorted(list(cats)) if len(cats) > 0 else sorted(list(product_cats))
    else:
        cats = set()
        for (f, c, p, pc, t) in key_to_col.keys():
            if f == flow and p == product:
                if type_str is None or t == type_str:
                    cats.add(pc)
        if not cats and type_str is not None:
            for (f, c, p, pc, t) in key_to_col.keys():
                if f == flow and p == product:
                    cats.add(pc)
        return sorted(list(cats)) if cats else sorted(list(product_cats))

def _update_snapshot_category_options():
    flow, product, product_cat, type_str = cur_snap()
    cats = available_categories_for_combo(flow, product, type_str)
    s_product_cat.options = cats
    if s_product_cat.value not in cats:
        if default_product_cat in cats:
            s_product_cat.value = default_product_cat
        else:
            s_product_cat.value = cats[0] if cats else default_product_cat

def _update_series_category_options():
    flow, country, product, product_cat, type_str = cur_series()
    cats = available_categories_for_combo(flow, product, type_str)
    x_product_cat.options = cats
    if x_product_cat.value not in cats:
        if default_product_cat in cats:
            x_product_cat.value = default_product_cat
        else:
            x_product_cat.value = cats[0] if cats else default_product_cat

# Snapshot update
no_map_div = Div(text="", width=972, height=20)  # Match figure width

def _set_slider_title(i: int):
    if 0 <= i < len(DATE_LABELS):
        month_slider.title = f"Month — {DATE_LABELS[i]}"

def update_snapshot_by_index(i: int):
    i = int(np.clip(i, 0, len(DATE_LIST)-1))
    _set_slider_title(i)

    flow, product, product_cat, type_str = cur_snap()
    row_date = pd.Timestamp(DATE_LIST[i]).strftime("%b %Y")

    country_exports = get_snapshot_for_date(flow, product, product_cat, type_str, i)
    
    filtered_world["exports"] = filtered_world["ADMIN"].map(
        lambda admin: country_exports.get(admin_to_df_map.get(admin), np.nan)
    )

    world_only_now = filtered_world["exports"].notna().sum() == 0
    
    # Keep map always visible - just show message div when no data
    # p.visible = not world_only_now  # REMOVED - map stays visible
    top15_chart.visible = not world_only_now
    no_map_div.visible = world_only_now
    if world_only_now:
        no_map_div.text = f"<i>No country breakdown for this selection on {row_date}. See series below.</i>"

    filtered_world["exports_log"] = _scale_values_for_map(flow, type_str)
    exports_log = filtered_world["exports_log"].astype(float).values
    if np.isfinite(exports_log).any():
        vmin = float(np.nanmin(exports_log)); vmax = float(np.nanmax(exports_log))
        if not np.isfinite(vmin): vmin = 0.0
        if not np.isfinite(vmax): vmax = 1.0
        if vmax == vmin: vmax = vmin + 1.0
    else:
        vmin, vmax = 0.0, 1.0

    filtered_world["note"] = filtered_world["exports"].apply(lambda x: "No Data" if pd.isnull(x) else "")
    filtered_world.loc[filtered_world["ADMIN"] == "China", "note"] = "Exporter (no data)"
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, vmin, vmax)

    # OPTIMIZATION: Update only the data fields, not geometry
    # Build value lookup
    value_lookup = {}
    for idx, data_row in filtered_world.iterrows():
        admin = data_row['ADMIN']
        value_lookup[admin] = {
            'exports': None if pd.isna(data_row['exports']) else float(data_row['exports']),
            'exports_log': None if pd.isna(data_row['exports_log']) else float(data_row['exports_log']),
            'note': data_row['note'],
            'custom_color': data_row['custom_color']
        }
    
    # Update patches data
    current_data = dict(geo_source.data)  # Get current data as dict
    # Create new lists for fields that will change
    new_exports = list(current_data['exports'])
    new_exports_log = list(current_data['exports_log'])
    new_notes = list(current_data['note'])
    new_colors = list(current_data['custom_color'])
    
    for i in range(len(current_data['ADMIN'])):
        admin = current_data['ADMIN'][i]
        if admin in value_lookup:
            new_exports[i] = value_lookup[admin]['exports']
            new_exports_log[i] = value_lookup[admin]['exports_log']
            new_notes[i] = value_lookup[admin]['note']
            new_colors[i] = value_lookup[admin]['custom_color']
    
    # Assign updated lists
    current_data['exports'] = new_exports
    current_data['exports_log'] = new_exports_log
    current_data['note'] = new_notes
    current_data['custom_color'] = new_colors
    
    # Trigger update
    geo_source.data = current_data

    p.title.text = f"China, {flow}, {product}, {product_cat}, {type_str}, {row_date}"
    color_mapper_obj.low = vmin
    color_mapper_obj.high = vmax
    color_bar.title = f"{flow}, {product}, {product_cat}, {type_str}"

    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []
    if not world_only_now:
        top = (filtered_world[['ADMIN','exports']].dropna()
            .sort_values('exports', ascending=False).head(15))
        terms_dict = {
            "United States of America": "US",
            "United Arab Emirates": "UAE",
            "United Kingdom": "UK",
            "Hong Kong S.A.R": 'Hong Kong'
        }
        labels = top['ADMIN'].replace(terms_dict)

        top15_table_source.data = dict(country=labels.tolist(), value=top['exports'].tolist())
        top15_chart_source.data = dict(country=labels.tolist(), value=top['exports'].tolist())
        top15_chart.x_range.factors = labels.tolist()
        top15_chart.title.text = f"{flow}, {product}, {product_cat}, {type_str}, {row_date}"

def reset_top15():
    flow, product, product_cat, type_str = cur_snap()
    filtered_world["exports_log"] = _scale_values_for_map(flow, type_str)
    exports_log = filtered_world["exports_log"].astype(float).values
    if np.isfinite(exports_log).any():
        vmin = float(np.nanmin(exports_log)); vmax = float(np.nanmax(exports_log))
        if not np.isfinite(vmin): vmin = 0.0
        if not np.isfinite(vmax): vmax = 1.0
        if vmax == vmin: vmax = vmin + 1.0
    else:
        vmin, vmax = 0.0, 1.0
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, vmin, vmax)
    
    # OPTIMIZATION: Update only colors
    value_lookup = {}
    for idx, data_row in filtered_world.iterrows():
        value_lookup[data_row['ADMIN']] = data_row['custom_color']
    
    current_data = dict(geo_source.data)  # Convert to plain dict
    new_colors = list(current_data['custom_color'])
    
    for i in range(len(current_data['ADMIN'])):
        admin = current_data['ADMIN'][i]
        if admin in value_lookup:
            new_colors[i] = value_lookup[admin]
    
    current_data['custom_color'] = new_colors
    geo_source.data = current_data
    
    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []

def highlight_top15():
    flow, product, product_cat, type_str = cur_snap()
    if is_world_only(flow, product, product_cat, type_str):
        return
    filtered_world["exports_log"] = _scale_values_for_map(flow, type_str)
    exports_log = filtered_world["exports_log"].astype(float).values
    valid_idx = np.where(np.isfinite(exports_log))[0]
    if len(valid_idx) == 0:
        return
    if len(valid_idx) > 15:
        top15_idx = valid_idx[np.argpartition(-exports_log[valid_idx], 15)[:15]]
    else:
        top15_idx = valid_idx

    colors = np.full(filtered_world.shape[0], "#dddddd", dtype=object)
    vmin = float(np.nanmin(exports_log[top15_idx])); vmax = float(np.nanmax(exports_log[top15_idx]))
    if not np.isfinite(vmin): vmin = 0.0
    if not np.isfinite(vmax): vmax = 1.0
    if vmax == vmin:
        idx = np.zeros(len(top15_idx), dtype=int)
    else:
        norm = (exports_log[top15_idx] - vmin) / (vmax - vmin)
        idx = (np.clip(norm, 0, 1) * (len(smooth_palette) - 1)).round().astype(int)
    for i, ci in enumerate(top15_idx):
        colors[ci] = smooth_palette[int(idx[i])]
    filtered_world["custom_color"] = colors
    
    # OPTIMIZATION: Update only colors
    value_lookup = {}
    for idx, data_row in filtered_world.iterrows():
        value_lookup[data_row['ADMIN']] = data_row['custom_color']
    
    current_data = dict(geo_source.data)  # Convert to plain dict
    new_colors = list(current_data['custom_color'])
    
    for i in range(len(current_data['ADMIN'])):
        admin = current_data['ADMIN'][i]
        if admin in value_lookup:
            new_colors[i] = value_lookup[admin]
    
    current_data['custom_color'] = new_colors
    geo_source.data = current_data

    terms_dict = {
        "United States of America": "US",
        "United Arab Emirates": "UAE",
        "United Kingdom": "UK",
        "Hong Kong S.A.R": 'Hong Kong'
    }
    top = (filtered_world.iloc[top15_idx][["ADMIN", "exports"]]
        .dropna()
        .sort_values("exports", ascending=False))
    labels = top["ADMIN"].replace(terms_dict)

    top15_table_source.data = dict(country=labels.tolist(), value=top["exports"].tolist())
    top15_chart_source.data = dict(country=labels.tolist(), value=top["exports"].tolist())
    top15_chart.x_range.factors = labels.tolist()

# Series explorer
def _update_series_country_options():
    flow, _, product, product_cat, type_str = cur_series()
    _update_series_category_options()
    cs = sorted(list(set(available_countries_for_combo(flow, product, product_cat, type_str)) | {"World"}))
    x_country_sel.options = cs
    if x_country_sel.value not in cs:
        x_country_sel.value = "World"

def _update_sa_toggle_state():
    """Enable/disable SA toggle based on data availability"""
    flow, country, product, product_cat, type_str = cur_series()
    sa_available = has_sa_data(flow, country, product, product_cat, type_str)
    x_sa_toggle.disabled = not sa_available
    if not sa_available:
        x_sa_toggle.active = False
    # Update label style to show availability
    if sa_available:
        x_sa_label.styles = {
            "font-family": "Georgia, serif",
            "font-size": "14px",
            "font-weight": "bold",
            "color": "#556B2F",
            "padding-top": "6px"
        }
    else:
        x_sa_label.styles = {
            "font-family": "Georgia, serif",
            "font-size": "14px",
            "font-weight": "bold",
            "color": "#999999",
            "padding-top": "6px"
        }

def _rebuild_series_table():
    """Rebuild table with current selection + all added series"""
    flow, country, product, product_cat, type_str = cur_series()

    # Use SA unit if toggle is active
    if x_sa_toggle.active:
        type_str = f"{type_str}, SA"

    # Get current selection data
    current_data = get_data_for_series(flow, country, product, product_cat, type_str)

    # Build table data with all series
    if len(current_data) == 0 and len(multi_series_data) == 0:
        series_table_source.data = dict(date=[])
        series_table.columns = [TableColumn(field="date", title="Date", width=date_width)]
        return

    # Create DataFrame with dates as index
    dates = current_data.index if len(current_data) > 0 else DATE_LIST
    table_df = pd.DataFrame(index=dates)

    # Add current selection as first column
    current_label = f"{flow}, {country}"
    if x_sa_toggle.active:
        current_label += " (SA)"
    table_df[current_label] = current_data.values if len(current_data) > 0 else [np.nan] * len(dates)

    # Add all added series
    for item in multi_series_data:
        src_data = item['source'].data
        if len(src_data['date']) > 0:
            series_df = pd.DataFrame({'value': src_data['value']}, index=pd.DatetimeIndex(src_data['date']))
            table_df[item['label']] = series_df['value'].reindex(table_df.index)

    # Take last 24 rows
    table_df = table_df.tail(24)

    # Build table data dict
    table_data = {'date': [pd.Timestamp(d).strftime('%Y-%m-%d') for d in table_df.index]}
    for col in table_df.columns:
        # Create safe field name
        safe_field = re.sub(r'[^a-zA-Z0-9_]', '_', col)
        table_data[safe_field] = table_df[col].tolist()

    series_table_source.data = table_data

    # Build table columns
    cols = [TableColumn(field="date", title="Date", width=date_width)]
    for col in table_df.columns:
        safe_field = re.sub(r'[^a-zA-Z0-9_]', '_', col)
        cols.append(TableColumn(field=safe_field, title=col, formatter=formatter, width=val_width))
    series_table.columns = cols

    # Expand table width based on number of columns
    series_table.width = date_width + (len(table_df.columns) * val_width)

def update_series_view():
    flow, country, product, product_cat, type_str = cur_series()

    # Update SA toggle availability
    _update_sa_toggle_state()

    # Use SA unit if toggle is active
    display_unit = type_str
    if x_sa_toggle.active:
        sa_unit = f"{type_str}, SA"
        display_unit = sa_unit
        type_str = sa_unit

    # Get series data
    series_data = get_data_for_series(flow, country, product, product_cat, type_str)

    dates = series_data.index.to_list()
    values = series_data.values.tolist()

    series_source.data = dict(date=dates, value=values)
    series_chart.title.text = f"China, {flow}, {country}, {product}, {product_cat}, {display_unit}"

    # Rebuild table with all series
    _rebuild_series_table()

# Callbacks
def _refresh_snapshot_for_current_index(attr, old, new):
    update_snapshot_by_index(int(month_slider.value))

for w in (s_flow, s_product, s_product_cat, s_type):
    w.on_change('value', _refresh_snapshot_for_current_index)

def _on_snapshot_product_change(attr, old, new):
    _update_snapshot_category_options()
    _refresh_snapshot_for_current_index(attr, old, new)

s_product.on_change('value', _on_snapshot_product_change)
s_flow.on_change('value', lambda a, o, n: _on_snapshot_product_change(a, o, n))
s_type.on_change('value', lambda a, o, n: _on_snapshot_product_change(a, o, n))

top15_button.on_click(highlight_top15)
reset_button.on_click(reset_top15)

def on_month_slider(attr, old, new):
    update_snapshot_by_index(int(new))
month_slider.on_change('value', on_month_slider)

def on_series_selector_change(attr, old, new):
    _update_series_country_options()
    update_series_view()
for w in (x_flow, x_product, x_product_cat, x_type):
    w.on_change('value', on_series_selector_change)
x_country_sel.on_change('value', lambda attr, old, new: update_series_view())

# SA toggle callback
x_sa_toggle.on_change('active', lambda attr, old, new: update_series_view())

# Multi-series functions
def add_series_to_chart():
    """Add current selection as a new series to the chart"""
    global multi_series_data

    flow, country, product, product_cat, type_str = cur_series()

    # Use SA unit if toggle is active
    if x_sa_toggle.active:
        type_str = f"{type_str}, SA"

    # Create unique key for this series
    series_key = (flow, country, product, product_cat, type_str)

    # Check if already added
    for item in multi_series_data:
        if item['key'] == series_key:
            return  # Already exists

    # Get series data
    series_data = get_data_for_series(flow, country, product, product_cat, type_str)
    dates = series_data.index.to_list()
    values = series_data.values.tolist()

    if len(dates) == 0:
        return  # No data

    # Create new source and renderer
    color_idx = len(multi_series_data) % len(SERIES_COLORS)
    color = SERIES_COLORS[color_idx]

    new_source = ColumnDataSource(data=dict(date=dates, value=values))
    new_line = series_chart.line(x="date", y="value", source=new_source,
                                  line_width=3, color=color)

    # Create label for legend (flow, country, product, category, unit, SA)
    unit_display = type_str.replace(', SA', '')
    short_label = f"{flow}, {country}, {product}, {product_cat}, {unit_display}"
    if x_sa_toggle.active:
        short_label += ", SA"

    # Add to tracking list
    multi_series_data.append({
        'source': new_source,
        'renderer': new_line,
        'label': short_label,
        'key': series_key,
        'color': color
    })

    # Update legend
    series_legend.items = [LegendItem(label=item['label'], renderers=[item['renderer']])
                          for item in multi_series_data]

    # Update range renderers to include primary line plus all added series
    series_xr.renderers = [line_ts] + [item['renderer'] for item in multi_series_data]
    series_yr.renderers = [line_ts] + [item['renderer'] for item in multi_series_data]

    # Rebuild table to include new series
    _rebuild_series_table()

def clear_all_series():
    """Remove all added series from the chart"""
    global multi_series_data

    # Hide all added series renderers
    for item in multi_series_data:
        item['renderer'].visible = False

    multi_series_data = []
    series_legend.items = []

    # Reset range renderers to just primary line
    series_xr.renderers = [line_ts]
    series_yr.renderers = [line_ts]

    # Rebuild table with just current selection
    _rebuild_series_table()

add_series_button.on_click(add_series_to_chart)
clear_series_button.on_click(clear_all_series)

# Play/Pause
ANIM_INTERVAL_MS = 600
_pc_handle = {"id": None}
def _advance_slider():
    if len(DATE_LIST) == 0:
        return
    i = int(month_slider.value)
    j = (i + 1) % len(DATE_LIST)
    month_slider.value = j
def _play():
    if _pc_handle["id"] is None:
        _pc_handle["id"] = curdoc().add_periodic_callback(_advance_slider, ANIM_INTERVAL_MS)
        play_button.disabled = True
        pause_button.disabled = False
def _pause():
    if _pc_handle["id"] is not None:
        curdoc().remove_periodic_callback(_pc_handle["id"])
        _pc_handle["id"] = None
        play_button.disabled = False
        pause_button.disabled = True
play_button.on_click(_play)
pause_button.on_click(_pause)

# Layout
app_title = Div(
    text="Mapping China's foreign trade",
    styles={"font-family":"Georgia, serif","font-size":"32px","font-weight":"bold","color":"#104b1f","margin-bottom":"20px"}
)

snapshot_heading = Div(
    text="<b>Global snapshot</b> — values by country at selected date",
    width=972,  # Match figure width
    styles={
        "font-family": "Georgia, serif", "font-size": "20px", "font-weight": "bold", "color": "black",
        "border-bottom": "2px solid #104b1f", "padding-bottom": "4px",
    },
)

series_heading = Div(
    text="<b>Time series</b>",
    width=972,  # Match figure width
    styles={
        "font-family": "Georgia, serif", "font-size": "20px", "font-weight": "bold", "color": "black",
        "border-bottom": "2px solid #104b1f", "padding-bottom": "4px",
    },
)

snapshot_controls = row(s_flow, s_product, s_product_cat, s_type)
snapshot_controls.width = 972  # Fixed to map width

snapshot_date_row = row(month_slider, play_button, pause_button)
snapshot_date_row.width = 972  # Fixed to map width

top15_buttons_row = row(top15_button, download_top15_button, reset_button, sizing_mode="stretch_width")
TOP15_ROWS_VISIBLE = 15
TOP15_ROW_HEIGHT = 26
TOP15_TABLE_HEIGHT = TOP15_ROWS_VISIBLE * TOP15_ROW_HEIGHT + 48

top15_table = DataTable(
    source=top15_table_source,
    columns=[
        TableColumn(field="country", title="Country", width=200),
        TableColumn(field="value", title="Value", formatter=formatter, width=150),
    ],
    width=370,
    row_height=TOP15_ROW_HEIGHT,
    height=TOP15_TABLE_HEIGHT,
    index_position=None,
    header_row=True,
)

top15_col = column(
    top15_buttons_row,
    top15_chart,
    Spacer(height=8),
    top15_table,
    width=370,  # Fixed width, no stretching
)

RIGHT_W = 370
GUTTER = 16

# Remove fixed widths - let elements use their natural size
left_col = column(
    snapshot_controls,
    snapshot_date_row,
    no_map_div,
    p,
    Div(
#        text="<i>Note: Map displays only trade flows ≥ $10M USD. Smaller values are excluded for performance.</i>",
        width=972,  # Match figure width
        styles={
            "font-family": "Georgia, serif",
            "font-size": "11px",
            "color": "#666",
            "font-style": "italic",
            "margin-top": "5px",
            "padding": "5px 10px",
            "background": "#f5f5f5",
            "border-left": "3px solid #556B2F"
        }
    ),
    width=972,  # Fixed to figure width
)

# Fixed width for top15 column
top15_col.width = RIGHT_W
top15_col.margin = (0, 0, 0, 0)

# Main row with fixed total width for consistency
snapshot_row_total_w = 972 + GUTTER + RIGHT_W  # 1358px total
main_row = row(
    left_col,
    Spacer(width=GUTTER),
    top15_col,
    width=snapshot_row_total_w,
)
main_row.styles = {"align-items": "flex-start"}

snapshot_section = column(
    snapshot_heading,
    main_row,
    width=snapshot_row_total_w,
)

# SERIES
series_left = column(series_chart, width=972)  # Match map width
series_right = column(
    series_table, 
    download_series_button,  # Moved here - below the table
    width=RIGHT_W
)

series_row_total_w = 972 + GUTTER + RIGHT_W  # 1358px total (same as snapshot)
series_row = row(
    series_left,
    Spacer(width=GUTTER),
    series_right,
    width=series_row_total_w,
)
series_row.styles = {"align-items": "flex-start"}

# Controls span full width - include SA toggle
sa_toggle_group = row(x_sa_label, x_sa_toggle, spacing=5)
# Series buttons group
series_buttons_group = row(add_series_button, clear_series_button, spacing=5)
series_controls = row(x_flow, x_country_sel, x_product, x_product_cat, x_type, Spacer(width=10), sa_toggle_group, Spacer(width=10), series_buttons_group)
series_controls.width = series_row_total_w

# Remove series_buttons row since button is now in series_right column

series_section = column(
    series_heading,
    series_controls,
    series_row,
    # series_buttons removed - button is now in series_right
    width=series_row_total_w,
)

# PAGE - Fixed width, left-aligned layout for consistency across devices
layout_total_w = 1358  # 972 + 16 + 370 (both sections have same width)
layout = column(
    app_title,
    snapshot_section,
    series_section,
    app_footnote,
    width=layout_total_w,
)

# Left-align the layout
layout.styles = {
    "margin": "0",  # Left-aligned
    "max-width": "1358px",  # Constrain max width
    "padding": "0 20px",  # Add padding on small screens
}

# Background syncing
def _sync_map_bg(attr, old, new):
    bg_map_src.data.update(
        x=[p.x_range.start], y=[p.y_range.start],
        w=[p.x_range.end - p.x_range.start], h=[p.y_range.end - p.y_range.start],
    )

def _sync_series_bg(attr, old, new):
    bg_series_src.data.update(
        x=[series_chart.x_range.start], y=[series_chart.y_range.start],
        w=[series_chart.x_range.end - series_chart.x_range.start], h=[series_chart.y_range.end - series_chart.y_range.start],
    )

layout.name = "app_root"

# Add inline CSS to force fixed, left-aligned layout
layout.styles = {
    "width": "1358px",
    "max-width": "1358px", 
    "margin": "0",  # Left-aligned
    "padding": "0 20px",
    "box-sizing": "border-box"
}

# Also force the sections to not stretch
snapshot_section.styles = {"width": "1358px", "max-width": "1358px"}
series_section.styles = {"width": "1358px", "max-width": "1358px"}

curdoc().add_root(layout)
curdoc().title = "China — Trade: Snapshot & Series"

# Loader hiding
_hide_loader_now = CustomJS(code="""
  const el = document.getElementById('bamboo-overlay');
  if (el) {
    el.style.opacity = '0';
    el.style.pointerEvents = 'none';
    el.style.display = 'none';
  }
""")
geo_source.js_on_change('data', _hide_loader_now)  # Use 'data' for ColumnDataSource, not 'geojson'
series_source.js_on_change('data', _hide_loader_now)

_fallback_hide = CustomJS(code="""
  setTimeout(() => {
    const el = document.getElementById('bamboo-overlay');
    if (el) { 
      el.style.opacity = '0'; 
      el.style.pointerEvents = 'none'; 
      el.style.display = 'none'; 
    }
  }, 6000);
""")

p.x_range.on_change('start', _sync_map_bg)
p.x_range.on_change('end', _sync_map_bg)
p.y_range.on_change('start', _sync_map_bg)
p.y_range.on_change('end', _sync_map_bg)
series_chart.x_range.on_change('start', _sync_series_bg)
series_chart.x_range.on_change('end', _sync_series_bg)
series_chart.y_range.on_change('start', _sync_series_bg)
series_chart.y_range.on_change('end', _sync_series_bg)

# Initial fill
_update_snapshot_category_options()
_update_series_category_options()
if len(DATE_LIST) > 0:
    print(f"[BOOT] Calling update_snapshot_by_index with index {len(DATE_LIST) - 1}")
    month_slider.value = len(DATE_LIST) - 1
    try:
        update_snapshot_by_index(month_slider.value)
        print("[BOOT] ✅ Initial map update completed")
    except Exception as e:
        print(f"[ERROR] Initial map update failed: {e}")
        import traceback
        traceback.print_exc()
else:
    month_slider.title = "Month"

_update_series_country_options()
try:
    update_series_view()
    print("[BOOT] ✅ Initial series update completed")
except Exception as e:
    print(f"[ERROR] Initial series update failed: {e}")
    import traceback
    traceback.print_exc()

# CSV downloads
_csv_js = """
function toCSV(data) {
  const cols = Object.keys(data);
  if (cols.length === 0) return "";
  const pretty = cols.map(c => c.replace(/_/g," "));
  const nrows = data[cols[0]].length;
  const lines = [pretty.join(",")];
  for (let i = 0; i < nrows; i++) {
    lines.push(cols.map(col => (data[col][i] == null ? "" : `"${data[col][i]}"`)).join(","));
  }
  return lines.join("\\n");
}
const csv = toCSV(source.data);
const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
const link = document.createElement("a");
link.href = URL.createObjectURL(blob);
link.download = filename;
document.body.appendChild(link);
link.click();
document.body.removeChild(link);
"""

download_series_button.js_on_click(CustomJS(
    args=dict(source=series_table_source, filename="series.csv"),
    code=_csv_js
))

download_top15_button.js_on_click(CustomJS(
    args=dict(source=top15_table_source, filename="top15.csv"),
    code=_csv_js
))

print("[BOOT] ===== INITIALIZATION COMPLETE =====")
print(f"[BOOT] Ready to serve requests")