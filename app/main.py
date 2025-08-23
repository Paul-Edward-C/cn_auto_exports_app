# app/main.py

import json
import re
import difflib
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import matplotlib.colors as mcolors

# --- OPTIONAL GeoPandas (fallback to GeoJSON if missing) ---
try:
    import geopandas as gpd
except ModuleNotFoundError:
    gpd = None

from bokeh.io import curdoc
from bokeh.models import (
    GeoJSONDataSource, Select, Button, ColumnDataSource, HoverTool, Div, Label,
    NumeralTickFormatter, DatetimeTickFormatter, DataTable, TableColumn,
    HTMLTemplateFormatter, ColorBar, LinearColorMapper, CustomJS, Spacer, DataRange1d,
    InlineStyleSheet, Slider
)
from bokeh.plotting import figure
from bokeh.layouts import column, row
from bokeh.themes import Theme
#from bokeh.events import DocumentReady


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DF_PATH = DATA_DIR / "auto_total.csv"
WORLD_SHP = DATA_DIR / "ne_10m_admin_0_countries.shp"
WORLD_GEOJSON = DATA_DIR / "ne_10m_admin_0_countries.geojson"

world = None
_using_gpd = False

try:
    if WORLD_GEOJSON.exists():
        with WORLD_GEOJSON.open('r', encoding='utf-8') as f:
            gj = json.load(f)
        # Make a DataFrame with properties + geometry in a column we’ll rename
        world = pd.DataFrame([feat["properties"] | {"__geom": feat["geometry"]} for feat in gj["features"]])
        _using_gpd = False
    elif gpd is not None and WORLD_SHP.exists():
        # Only try shapefile if GeoJSON isn't bundled
        world = gpd.read_file(WORLD_SHP.as_posix())
        _using_gpd = True
    else:
        raise FileNotFoundError("No world shapefile/geojson found in data/")
except Exception as e:
    # If shapefile load fails (typical on Heroku), retry with GeoJSON if available
    if WORLD_GEOJSON.exists():
        with WORLD_GEOJSON.open('r', encoding='utf-8') as f:
            gj = json.load(f)
        world = pd.DataFrame([feat["properties"] | {"__geom": feat["geometry"]} for feat in gj["features"]])
        _using_gpd = False
    else:
        raise RuntimeError(f"Failed to load world geometry: {e}")

# Normalize geometry column name so downstream code can always use 'geometry'
if not _using_gpd and 'geometry' not in world.columns and '__geom' in world.columns:
    world = world.rename(columns={'__geom': 'geometry'}) 
# =============================================================================
# THEME
# =============================================================================
theme_json = {
    'attrs': {
        'figure': {'background_fill_color': '#228B22','background_fill_alpha': 0.05,},
        'Axis':   {'axis_label_text_font': 'Georgia','major_label_text_font': 'Georgia',},
        'Title':  {'text_font_style': 'bold','text_font': 'Georgia','text_font_size': '18px',},
        'Legend': {'label_text_font': 'Georgia','padding': 1,'spacing': 1,'background_fill_alpha': 0.7,},
        "Label": {
          "text_font": "Georgia",
          "text_font_size": "0.875em",
          "text_font_style": "bold",
          "text_color": "#556B2F",
          "text_align": "left",
          "text_baseline": "bottom",
     #     "background_fill_color": "white",
          "background_fill_alpha": 1.0,
          "border_line_alpha": 0.3,
          "border_line_width": 0.5,
          "border_line_color": "#A9A9A9",
          "padding": 5
      }
    }
}
curdoc().theme = Theme(json=theme_json)

# =============================================================================
# PALETTE
# =============================================================================
color_map = {
    'c1': '#556B2F', 'c2': '#B7410E', 'c3': '#4682B4', 'c4': '#FF7F50',
    'c5': '#228B22', 'c6': '#FFBF00', 'c7': '#87CEEB', 'c8': '#FFDB58',
    'c9': '#6B8E23', 'c10': '#CD5C5C'
}
custom_palette = [
    color_map['c7'], color_map['c3'], color_map['c8'],
    color_map['c6'], color_map['c4'], color_map['c2'], color_map['c10']
]
def interpolate_palette(palette, n):
    cmap = mcolors.LinearSegmentedColormap.from_list('custom', palette)
    return [mcolors.to_hex(cmap(i/(n-1))) for i in range(n)]
smooth_palette = interpolate_palette(custom_palette, 50)

# Shared HTML formatter (Top-15 & Series tables)
formatter = HTMLTemplateFormatter(
    template="""
    <style>
        .slick-column-name {font-family: Georgia; font-weight: 900; font-size: 0.9rem;}
        .slick-header-column {background-color: hsla(120, 100%, 25%, 0.1) !important;}
        .slick-cell {font-family: Georgia; font-size: 0.9rem;}
        .slick-row:nth-of-type(even) {background-color: hsla(120, 100%, 25%, 0.1) !important;}
    </style>
    <%= (value != null) ? value.toFixed(2) : "N/A" %>
    """
)

# =============================================================================
# DATA LOAD
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DF_PATH = DATA_DIR / "auto_total.csv"
WORLD_SHP = DATA_DIR / "ne_10m_admin_0_countries.shp"
WORLD_GEOJSON = DATA_DIR / "ne_10m_admin_0_countries.geojson"


df = pd.read_csv(DF_PATH.as_posix())

def _normalize_header(s: str) -> str:
    s = (s or "")
    s = s.replace("\ufeff", "")        # BOM
    s = s.replace("\xa0", " ")         # NBSP
    parts = [p.strip() for p in s.split(",")]
    return ", ".join(parts)

df.columns = [_normalize_header(c) for c in df.columns]

# Detect & prepare date column
date_col = next((c for c in df.columns if re.search(r'date', c, re.IGNORECASE)), None)
if not date_col:
    raise RuntimeError("No 'date' column found (case-insensitive) in app/data/auto_total.csv")

df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
df = df.sort_values(date_col).reset_index(drop=True)

# unique, sorted normalized ticks (list of months we allow)
_norm_all = df[date_col].dropna().dt.normalize()
_date_uni = _norm_all.drop_duplicates().sort_values()

# Python datetime list and pretty labels
DATE_LIST = [d.to_pydatetime() for d in _date_uni]
DATE_LABELS = [pd.Timestamp(d).strftime("%b %Y") for d in DATE_LIST]

# For each unique date, pick the **last** row index with that date (stable)
_last_idx = _norm_all.groupby(_norm_all).apply(lambda s: s.index[-1])
DATE_ROW_IDXS = [int(_last_idx.loc[pd.Timestamp(d)]) for d in _date_uni]

def latest_date_label(fmt="%b %Y"):
    dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
    return dates.max().strftime(fmt) if not dates.empty else "Latest"

# =============================================================================
# WORLD GEOMETRY LOAD (with fallback)
# =============================================================================
WORLD_SHP = Path('app/data/ne_10m_admin_0_countries.shp')
WORLD_GEOJSON = Path('app/data/ne_10m_admin_0_countries.geojson')

if gpd is not None and WORLD_SHP.exists():
    world = gpd.read_file(WORLD_SHP.as_posix())
    _using_gpd = True
elif WORLD_GEOJSON.exists():
    with WORLD_GEOJSON.open('r', encoding='utf-8') as f:
        gj = json.load(f)
    world = pd.DataFrame([feat["properties"] | {"__geom": feat["geometry"]} for feat in gj["features"]])
    _using_gpd = False
else:
    raise FileNotFoundError("No world shapefile/geojson found in app/data/")

# Normalize geometry column name
if not _using_gpd and 'geometry' not in world.columns and '__geom' in world.columns:
    world = world.rename(columns={'__geom': 'geometry'})

# =============================================================================
# SCHEMA PARSER
# Expected wide columns: "China, {Flow}, {Country}, {Product}, {Product_cat}, {Unit}"
# =============================================================================
key_to_col = {}  # (flow, country, product, product_cat, unit) -> column
flows, countries, products, product_cats, types_set = set(), set(), set(), set(), set()

def parse_schema(colname: str):
    parts = [p.strip() for p in colname.split(",")]
    if len(parts) >= 6 and parts[0].lower() == "china":
        flow        = parts[1]
        country     = parts[2]
        product     = parts[3]
        product_cat = parts[4]
        unit        = ", ".join(parts[5:]).strip()   # allow commas in unit
        return (flow, country, product, product_cat, unit)
    return None

for col in df.columns:
    parsed = parse_schema(col)
    if parsed is None:
        continue
    flow, country, product, product_cat, unit = parsed
    key_to_col[(flow, country, product, product_cat, unit)] = col
    flows.add(flow); countries.add(country); products.add(product); product_cats.add(product_cat); types_set.add(unit)

for _col in set(key_to_col.values()) & set(df.columns):
    df[_col] = pd.to_numeric(
        df[_col].astype(str)
                 .str.replace(',', '', regex=False)   # remove thousands sep
                 .str.replace('\u202f', '', regex=False)  # narrow no-break space
                 .str.replace('\xa0', '', regex=False)    # NBSP
                 .str.strip(),
        errors='coerce'
    )


def pick_default(options, preferred=None):
    if preferred and preferred in options:
        return preferred
    return sorted(list(options))[0] if options else None

default_flow        = pick_default(flows, 'Exports')
default_product     = pick_default(products, 'Autos')
default_product_cat = pick_default(product_cats, 'Total')
default_type        = pick_default(types_set, 'USD m')

# =============================================================================
# COUNTRY MATCHING for MAP
# =============================================================================
country_list = sorted([c for c in countries if c != 'World'])

def has_match(admin_name):
    match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
    return bool(match)

filtered_world = world[world['ADMIN'].apply(has_match)].reset_index(drop=True)
if 'geometry' not in filtered_world.columns and '__geom' in filtered_world.columns:
    filtered_world = filtered_world.rename(columns={'__geom': 'geometry'})

admin_to_df_map = {}
for admin_name in filtered_world['ADMIN']:
    match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
    admin_to_df_map[admin_name] = match[0] if match else None

# add China row if missing (for consistent note)
if not (filtered_world["ADMIN"] == "China").any():
    china_row = world[world["ADMIN"] == "China"]
    if not china_row.empty:
        if 'geometry' not in china_row.columns and '__geom' in china_row.columns:
            china_row = china_row.rename(columns={'__geom': 'geometry'})
        filtered_world = pd.concat([filtered_world, china_row], ignore_index=True)

# =============================================================================
# HELPERS
# =============================================================================
def available_countries_for_combo(flow, product, product_cat, type_str):
    return [c for c in countries if (flow, c, product, product_cat, type_str) in key_to_col]

def is_world_only(flow, product, product_cat, type_str):
    cs = available_countries_for_combo(flow, product, product_cat, type_str)
    return (len([c for c in cs if c != 'World']) == 0)

def is_currency_type(type_str):
    return bool(re.search(r'\b(USD|CNY)\b', type_str)) and bool(re.search(r'\b(bn|m)\b', type_str))

def should_log(flow, type_str):
    if flow == 'Balance':
        return False
    return is_currency_type(type_str)

def world_to_geojson(df_like):
    cols = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    df_like = df_like[cols]
    if _using_gpd:
        return df_like.to_json()
    feats = []
    for _, r in df_like.iterrows():
        props = {k: r.get(k, None) for k in ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color']}
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
    else:
        idx[mask] = 0
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
    """Return a float Series to drive the color scale.
       - If log scaling is desired AND min value >= 0: use log1p (keeps 0).
       - Otherwise: use linear values (so negatives are kept & colored)."""
    vals = pd.to_numeric(filtered_world["exports"], errors="coerce")
    if should_log(flow, type_str):
        try:
            minv = float(np.nanmin(vals.values))
        except Exception:
            minv = np.nan
        if np.isfinite(minv) and minv >= 0:
            # include zeros: log1p(0)=0 (not gray)
            return vals.apply(lambda x: np.log1p(x) if pd.notnull(x) else np.nan).astype(float)
        # negatives exist → fall back to linear so they’re not gray
    return vals.astype(float)

# =============================================================================
# WIDGETS (two independent sections)
# =============================================================================
# Snapshot controls: NO country selector
s_flow        = Select(title="Flow", value=default_flow, options=sorted(list(flows)), width=160)
s_product     = Select(title="Product", value=default_product, options=sorted(list(products)), width=180)
s_product_cat = Select(title="Category", value=default_product_cat, options=sorted(list(product_cats)), width=200)
s_type        = Select(title="Unit", value=default_type, options=sorted(list(types_set)), width=140)
def cur_snap():
    return (s_flow.value, s_product.value, s_product_cat.value, s_type.value)

# Series explorer controls: WITH country selector (incl. World)
x_flow        = Select(title="Flow", value=default_flow, options=sorted(list(flows)), width=160)
x_product     = Select(title="Product", value=default_product, options=sorted(list(products)), width=180)
x_product_cat = Select(title="Category", value=default_product_cat, options=sorted(list(product_cats)), width=200)
x_type        = Select(title="Unit", value=default_type, options=sorted(list(types_set)), width=140)
x_country_sel = Select(title="Country", value="World", options=["World"], width=220)
def cur_series():
    return (x_flow.value, x_country_sel.value, x_product.value, x_product_cat.value, x_type.value)

# Snapshot month slider (INTEGER index)
month_slider = Slider(title="", start=0, end=max(len(DATE_LIST)-1, 0),
                      value=max(len(DATE_LIST)-1, 0), step=1, width=500)

# Play / Pause
play_button  = Button(label="► Play", width=70)
pause_button = Button(label="❚❚ Pause", width=90, disabled=True)


app_footnote = Div(
    text="Source: EAE, CCA",
    width=980,
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

# =============================================================================
# DATA SOURCES
# =============================================================================
filtered_world["exports"] = np.nan
filtered_world["exports_log"] = np.nan
filtered_world["note"] = ""
filtered_world["custom_color"] = "#dddddd"
columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
geo_source = GeoJSONDataSource(geojson=world_to_geojson(filtered_world[columns_to_keep]))

top15_table_source  = ColumnDataSource(data=dict(country=[], value=[]))
top15_chart_source  = ColumnDataSource(data=dict(country=[], value=[]))

series_source       = ColumnDataSource(data=dict(date=[], value=[]))
series_table_source = ColumnDataSource(data=dict(index=[], date=[], value=[]))

# =============================================================================
# FIGURES
# =============================================================================
TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"
latest_label = latest_date_label()
p = figure(
    title=f"China , {default_flow} by country, {default_product}, {default_product_cat}, {default_type}, {latest_label})",
    tools=TOOLS, x_axis_location=None, y_axis_location=None,
    active_scroll='wheel_zoom', width=950, height=520,
)
p.grid.grid_line_color = None
# fix initial ranges to shapefile bounds so background can size correctly
xmin, ymin, xmax, ymax = filtered_world.total_bounds
p.x_range.start, p.x_range.end = float(xmin), float(xmax)
p.y_range.start, p.y_range.end = float(ymin), float(ymax)

color_mapper_obj = LinearColorMapper(palette=smooth_palette, low=0.0, high=1.0, nan_color="#dddddd")
color_bar = ColorBar(color_mapper=color_mapper_obj, label_standoff=12, location=(0,0),
                     title=f"{default_flow} , {default_product}, {default_product_cat}, {default_type}")
p.add_layout(color_bar, 'right')
p.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=f"www.eastasiaecon.com/cn/#charts"))
#source_note = Label(
#    x=p.width - 10, y=10, x_units='screen', y_units='screen',
#    text="Source: CCA, EAE", text_align='right', text_baseline='bottom',
#    text_font='Georgia', text_font_style='normal', text_font_size='10pt',
#)
#p.add_layout(source_note)
#p.js_on_event('reset', CustomJS(args=dict(lbl=source_note, plt=p), code="lbl.x = plt.width - 10; lbl.y = 10;"))

patches = p.patches('xs', 'ys', source=geo_source, fill_color='custom_color',
    fill_alpha=0.7, line_color="gray", line_width=0.5)
hover = p.select_one(HoverTool)
hover.point_policy = "follow_mouse"
hover.tooltips = [("Country", "@ADMIN"), ("Value", "@exports{0,0.00}"), ("Note", "@note")]

# --- MAP WATERMARK BACKGROUND (underlay, synced to ranges) ---
BACKGROUND_URL = "https://www.eastasiaecon.com/content/images/size/w2400/2023/04/Image-29-4-2023-at-7.34-PM.jpeg"
bg_map_src = ColumnDataSource(dict(url=[BACKGROUND_URL], x=[p.x_range.start], y=[p.y_range.start],
                                   w=[p.x_range.end - p.x_range.start], h=[p.y_range.end - p.y_range.start]))
p.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_map_src,
            anchor="bottom_left", global_alpha=0.18, level="underlay")

sync_map_js = CustomJS(args=dict(src=bg_map_src, xr=p.x_range, yr=p.y_range), code="""
    const u = src.data.url;
    src.data = { url: u, x:[xr.start], y:[yr.start], w:[xr.end-xr.start], h:[yr.end-yr.start] };
    src.change.emit();
""")
for prop in ("start","end"):
    p.x_range.js_on_change(prop, sync_map_js)
    p.y_range.js_on_change(prop, sync_map_js)

# --- Top 15 bar
top15_chart = figure(
    x_range=[], height=350, width=370,
    title=f"{default_flow}, {default_product}, {default_product_cat}, {default_type} {latest_label}",
    toolbar_location=None, tools="", min_border_left=10, min_border_right=10, min_border_top=10, min_border_bottom=10
)
top15_chart.vbar(x="country", top="value", source=top15_chart_source, width=0.7, color="#556B2F", alpha=0.7)
top15_chart.xaxis.major_label_orientation = 1.0
top15_chart.xgrid.grid_line_color = None
top15_chart.title.text_font_size = "14px"

# --- Series explorer line chart (auto-scale with DataRange1d) ---
series_xr = DataRange1d(only_visible=True, range_padding=0.02)
series_yr = DataRange1d(only_visible=True, range_padding=0.08)

series_chart = figure(
    height=260, width=980, title="Series",
    x_axis_type="datetime",
    x_range=series_xr, y_range=series_yr,
    tools="pan,xwheel_zoom,box_zoom,reset,save",
    margin=(20, 10, 10, 10)
)

line_ts = series_chart.line(x="date", y="value", source=series_source, line_width=2)
pts_ts  = series_chart.circle(x="date", y="value", source=series_source, size=5, alpha=0.15)


def _lock_series_rangers():
    # Restrict auto-ranging to the data renderers (not the background image)
    series_xr.renderers = [line_ts, pts_ts]
    series_yr.renderers = [line_ts, pts_ts]
    # Nudge the background once to the current range
    xs, xe = series_chart.x_range.start, series_chart.x_range.end
    ys, ye = series_chart.y_range.start, series_chart.y_range.end
    if xs is not None and xe is not None and ys is not None and ye is not None:
        bg_series_src.data.update(x=[xs], y=[ys], w=[xe - xs], h=[ye - ys])

curdoc().add_next_tick_callback(_lock_series_rangers)
# tell DataRange1d to ONLY use these renderers (ignores background image)
##series_xr.renderers = [line_ts, pts_ts]
#series_yr.renderers = [line_ts, pts_ts]

hover_ts = HoverTool(
    renderers=[pts_ts],
    tooltips=[("Date", "@date{%b %Y}"), ("Value", "@value{0,0.00}")],
    formatters={"@date": "datetime"},
    mode="vline"
)
series_chart.add_tools(hover_ts)
series_chart.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
series_chart.xaxis.formatter = DatetimeTickFormatter(years="%b-%y", months="%b-%y")
series_chart.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=f"www.eastasiaecon.com/cn/#charts"))
# --- Background image that always fills the plot frame ---
bg_series_src = ColumnDataSource(dict(url=[BACKGROUND_URL], x=[0], y=[0], w=[1], h=[1]))
series_bg_renderer = series_chart.image_url(
    url='url', x='x', y='y', w='w', h='h', source=bg_series_src,
    anchor="bottom_left", global_alpha=0.12, level="underlay"
)

update_bg_js = CustomJS(args=dict(xr=series_xr, yr=series_yr, bg=bg_series_src), code="""
    const xs = xr.start, xe = xr.end, ys = yr.start, ye = yr.end;
    if (xs == null || xe == null || ys == null || ye == null) return;
    bg.data.x = [xs];
    bg.data.y = [ys];
    bg.data.w = [xe - xs];
    bg.data.h = [ye - ys];
    bg.change.emit();
""")
for prop in ("start", "end"):
    series_xr.js_on_change(prop, update_bg_js)
    series_yr.js_on_change(prop, update_bg_js)
#series_chart.js_on_event(DocumentReady, update_bg_js)

# =============================================================================
# TABLES & BUTTONS
# =============================================================================
date_width = 200
val_width  = 150

# Series table uses the SAME HTML template formatter as Top-15
series_columns = [
    TableColumn(field="date",  title="Date", width=date_width),
    TableColumn(field="value", title="Value", formatter=formatter, width=val_width),
]
series_table = DataTable(
    source=series_table_source,
    columns=series_columns,
    width=date_width + val_width,
    height=320,
    index_position=None,
    header_row=True
)

top15_button = Button(label="Highlight Top 15", button_type="success", width=220, height=35)
reset_button = Button(label="🔄", button_type="default", width=40, height=35)
download_series_button = Button(label="Download Series CSV", button_type="primary", width=220, height=35)
download_top15_button  = Button(label="Download Top 15 CSV", button_type="primary", width=220, height=35)

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

btn_sheet     = InlineStyleSheet(css=BTN_CSS)
reset_sheet   = InlineStyleSheet(css=RESET_CSS)
selects_sheet = InlineStyleSheet(css=SELECTS_CSS)

for b in [top15_button, download_top15_button, download_series_button]:
    b.stylesheets = [btn_sheet]
reset_button.stylesheets = [reset_sheet]

for w in (s_flow, s_product, s_product_cat, s_type,
          x_flow, x_product, x_product_cat, x_type, x_country_sel):
    w.stylesheets = [selects_sheet]

for b in [top15_button, download_top15_button, download_series_button]:
    b.css_classes = ["styled-btn"]
reset_button.css_classes = ["icon-btn"]

# =============================================================================
# SNAPSHOT (MAP) UPDATE — INDEXED BY MONTH
# =============================================================================
no_map_div = Div(text="", width=980, height=20)

def _set_slider_title(i: int):
    if 0 <= i < len(DATE_LABELS):
        month_slider.title = f"Month — {DATE_LABELS[i]}"

def _row_for_index(i: int) -> int:
    if not DATE_ROW_IDXS:
        return len(df) - 1
    i = int(np.clip(i, 0, len(DATE_ROW_IDXS)-1))
    return DATE_ROW_IDXS[i]

def update_snapshot_by_index(i: int):
    i = int(np.clip(i, 0, len(DATE_LIST)-1))
    _set_slider_title(i)

    flow, product, product_cat, type_str = cur_snap()
    row_idx = _row_for_index(i)
    row = df.iloc[row_idx]
    row_date = pd.to_datetime(row[date_col]).strftime("%b %Y")

    country_exports = {}
    for admin_name, df_country in admin_to_df_map.items():
        key = (flow, df_country, product, product_cat, type_str)
        col = key_to_col.get(key)
        if col and col in df.columns:
            val = row[col]
            # ensure numeric (handles any str leftovers)
            try:
                val = float(val)
            except Exception:
                val = np.nan
        else:
            val = np.nan
        country_exports[admin_name] = val

    filtered_world["exports"] = filtered_world["ADMIN"].map(country_exports)

    world_only_now = filtered_world["exports"].notna().sum() == 0
    p.visible = not world_only_now
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

    geo_source.geojson = world_to_geojson(filtered_world[columns_to_keep])

    p.title.text = f"China, {flow} by country, {product}, {product_cat}, {type_str}, {row_date}"
    color_mapper_obj.low = vmin
    color_mapper_obj.high = vmax
    color_bar.title = f"{flow}, {product}, {product_cat},{type_str}"

    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []
    if not world_only_now:
        top = (filtered_world[['ADMIN','exports']]
               .dropna()
               .sort_values('exports', ascending=False)
               .head(15))
        top15_table_source.data = dict(country=top['ADMIN'].tolist(), value=top['exports'].tolist())
        top15_chart_source.data = dict(country=top['ADMIN'].tolist(), value=top['exports'].tolist())
        top15_chart.x_range.factors = top['ADMIN'].tolist()
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
    geo_source.geojson = world_to_geojson(filtered_world[columns_to_keep])
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
    geo_source.geojson = world_to_geojson(filtered_world[columns_to_keep])

    top = (filtered_world.iloc[top15_idx][["ADMIN", "exports"]]
           .dropna()
           .sort_values("exports", ascending=False))
    top15_table_source.data = dict(country=top["ADMIN"].tolist(), value=top["exports"].tolist())
    top15_chart_source.data = dict(country=top["ADMIN"].tolist(), value=top["exports"].tolist())
    top15_chart.x_range.factors = top["ADMIN"].tolist()

# =============================================================================
# SERIES EXPLORER UPDATE
# =============================================================================
def _get_series_col(flow, country, product, product_cat, type_str):
    return key_to_col.get((flow, country, product, product_cat, type_str))

def _get_series_timeseries(flow, country, product, product_cat, type_str):
    col = _get_series_col(flow, country, product, product_cat, type_str)
    if not col:
        return dict(date=[], value=[])
    dates = df[date_col].tolist()
    vals = df[col].apply(lambda x: round(x, 2) if pd.notnull(x) else None).tolist()
    return dict(date=dates, value=vals)

def _update_series_country_options():
    flow, _, product, product_cat, type_str = cur_series()
    cs = sorted(list(set(available_countries_for_combo(flow, product, product_cat, type_str)) | {"World"}))
    x_country_sel.options = cs
    if x_country_sel.value not in cs:
        x_country_sel.value = "World"

def update_series_view():
    flow, country, product, product_cat, type_str = cur_series()
    data = _get_series_timeseries(flow, country, product, product_cat, type_str)

    # update chart
    series_source.data = data
    series_chart.title.text = f"China , {flow}, {country}, {product}, {product_cat}, {type_str}"

    # update bottom table (last 24 rows)
    if len(data["date"]) > 0:
        dates_ser = pd.to_datetime(pd.Series(data["date"]), errors="coerce")
        vals_ser  = pd.to_numeric(pd.Series(data["value"]), errors="coerce")
        last      = pd.DataFrame({"date": dates_ser, "value": vals_ser}).tail(24)
        series_table_source.data = dict(
            index=list(range(len(last))),
            date=last["date"].dt.strftime('%Y-%m-%d').tolist(),
            value=last["value"].tolist()
        )
    else:
        series_table_source.data = dict(index=[], date=[], value=[])

# =============================================================================
# CALLBACKS
# =============================================================================
def _refresh_snapshot_for_current_index(attr, old, new):
    update_snapshot_by_index(int(month_slider.value))

for w in (s_flow, s_product, s_product_cat, s_type):
    w.on_change('value', _refresh_snapshot_for_current_index)

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

# Play / Pause
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

# =============================================================================
# TITLES & LAYOUT (with bigger Georgia section titles)
# =============================================================================
app_title = Div(
    text="China, Foreign trade",
    styles={"font-family":"Georgia, serif","font-size":"26px","font-weight":"bold","color":"#104b1f","margin-bottom":"14px"}
)

snapshot_heading = Div(
    text="<b>Global snapshot</b> — values by country at selected date",
    width=980,
    styles={
        "font-family": "Georgia, serif",
        "font-size": "20px",
        "font-weight": "bold",
        "color": "black",
        "border-bottom": "2px solid #104b1f",
        "padding-bottom": "4px",
    },
)

series_heading = Div(
    text="<b>Time series</b>",
    width=980,
    styles={
        "font-family": "Georgia, serif",
        "font-size": "20px",
        "font-weight": "bold",
        "color": "black",
        "border-bottom": "2px solid #104b1f",
        "padding-bottom": "4px",
    },
)

snapshot_controls = row(s_flow, s_product, s_product_cat, s_type, sizing_mode="fixed")
snapshot_date_row = row(month_slider, play_button, pause_button)

top15_buttons_row = row(top15_button, download_top15_button, reset_button, sizing_mode="fixed")
top15_col = column(
    top15_buttons_row,
    top15_chart,
    Spacer(height=8),
    DataTable(source=top15_table_source,
              columns=[TableColumn(field="country", title="Country", width=200),
                       TableColumn(field="value", title="Value", formatter=formatter, width=150)],
              width=370, height=350, index_position=None, header_row=True),
    sizing_mode="fixed",
    width=370
)
main_row = row(p, top15_col, sizing_mode="stretch_width")
snapshot_section = column(
    snapshot_heading,
    snapshot_controls,
    snapshot_date_row,
    no_map_div,
    main_row,
)

series_controls = row(x_flow, x_country_sel, x_product, x_product_cat, x_type, sizing_mode="fixed")
series_row = row(series_chart, series_table, sizing_mode="fixed")
series_buttons = row(download_series_button, sizing_mode="fixed")
series_section = column(
    series_heading,
    series_controls,
    series_row,
    series_buttons
)

layout = column(app_title, snapshot_section, series_section, app_footnote, sizing_mode="stretch_width")
curdoc().add_root(layout)
curdoc().title = "China — Trade: Snapshot & Series"

# =============================================================================
# CSV DOWNLOADS
# =============================================================================
download_series_button.js_on_click(CustomJS(args=dict(source=series_table_source), code="""
    function toCSV(data) {
        const cols = Object.keys(data);
        if (cols.length === 0) { return ""; }
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
    link.download = "series.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
"""))

download_top15_button.js_on_click(CustomJS(args=dict(source=top15_table_source), code="""
    function toCSV(data) {
        const cols = Object.keys(data);
        if (cols.length === 0) { return ""; }
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
    link.download = "top15.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
"""))

# =============================================================================
# INITIAL FILL
# =============================================================================
if len(DATE_LIST) > 0:
    month_slider.value = len(DATE_LIST)-1
    update_snapshot_by_index(month_slider.value)
else:
    month_slider.title = "Month"

def _init_series():
    _update_series_country_options()
    update_series_view()
_init_series()

def _sync_backgrounds():
    bg_map_src.data.update(
        x=[p.x_range.start], y=[p.y_range.start],
        w=[p.x_range.end - p.x_range.start], h=[p.y_range.end - p.y_range.start]
    )
    bg_series_src.data.update(
        x=[series_chart.x_range.start], y=[series_chart.y_range.start],
        w=[series_chart.x_range.end - series_chart.x_range.start],
        h=[series_chart.y_range.end - series_chart.y_range.start]
    )
curdoc().add_next_tick_callback(_sync_backgrounds)

print("[BOOT] CSV path:", DF_PATH.as_posix())
print("[BOOT] CSV shape:", df.shape)
print("[BOOT] date_col:", date_col, "dates:", df[date_col].dropna().shape[0])
print("[BOOT] schema counts -> flows:", len(flows), "countries:", len(countries),
      "products:", len(products), "types:", len(types_set), "cols indexed:", len(key_to_col))

# Example default combo available by country?
_default_combo = (default_flow, default_product, default_product_cat, default_type)
_avail = [c for c in countries if (default_flow, c, default_product, default_product_cat, default_type) in key_to_col]
print("[BOOT] Default combo:", _default_combo, "country cols:", len(_avail))
