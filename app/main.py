"""China trade dashboard (two-chart framework, ported from region_auto_bokeh).

China is the only reporter. World map (pick a partner) + a line chart of up to four user-built
series. Workflow: choose Flow / Product / Product-category / Unit, pick a partner (click the map,
or the Country / Region / World boxes), then 'Add to chart'. Up to four series — any mix of
flow / partner / product / category / unit — plot together; a list lets you remove them.

    /Users/paul/opt/anaconda3/bin/bokeh serve --show main.py
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (ColumnDataSource, Select, Button, HoverTool, Div,
                          LinearColorMapper, ColorBar, DataRange1d, LinearAxis,
                          NumeralTickFormatter, DatetimeTickFormatter, Span,
                          Label, SaveTool, Legend, LegendItem,
                          DataTable, TableColumn, HTMLTemplateFormatter,
                          CustomJS)
from bokeh.plotting import figure

HERE = Path(__file__).parent
DATA_PARQUET = HERE / 'data' / 'cn_long.parquet'

# ---------------------------------------------------------------- house style
FONT = 'Georgia'
BRAND = '#556B2F'
PANEL_BG = '#f4f9f4'
REPORTER = 'China'                                   # the only reporter
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

# ---------------------------------------------------------------- data
DATA = pd.read_parquet(DATA_PARQUET)       # string columns are categorical (~90 MB)
DATA['Date'] = pd.to_datetime(DATA['Date'])
CUR = DATA['Date'].max()
# MultiIndex for O(log n) .loc lookups. The parquet is pre-sorted by these keys, so set_index
# yields a monotonic index — only sort defensively if that ever isn't the case.
IDX = (DATA[['flow', 'product', 'product_cat', 'unit', 'iso3', 'Date', 'value']]
       .set_index(['flow', 'product', 'product_cat', 'unit', 'iso3']))
if not IDX.index.is_monotonic_increasing:
    IDX = IDX.sort_index()

# Region aggregates (iso3 'R_*', not on the map) — selected via the Region dropdown.
_agg = DATA[DATA['iso3'].astype(str).str.startswith('R_')][['country', 'iso3']].drop_duplicates()
REGION_ISO = dict(zip(_agg['country'], _agg['iso3']))
REGION_LABELS = sorted(REGION_ISO)
REGION_OF = json.loads((DATA_PARQUET.parent / 'region_map.json').read_text())   # iso3 -> region

# Dimension options. Product-category cascades from Product (e.g. Semis has ICs…, Autos has ICE…).
_FLOW_ORDER = ['Exports', 'Imports', 'Trade balance']
_PROD_ORDER = ['Total', 'Autos', 'Semis', 'Batteries', 'Solar', 'Rare earths', 'Industrial robots']
_UNIT_ORDER = ['USD bn', 'USD bn, SA', 'USD mn', 'Unit', 'Unit mn', 'KG mn', 'KG', 'Carat', '-']

def _order(values, pref):
    s = set(values)
    return [v for v in pref if v in s] + sorted(v for v in s if v not in pref)

FLOWS = _order(DATA['flow'].unique(), _FLOW_ORDER)
PRODUCTS = _order(DATA['product'].unique(), _PROD_ORDER)
UNITS = _order(DATA['unit'].unique(), _UNIT_ORDER)
PRODUCT_CATS = {p: _order(DATA.loc[DATA['product'] == p, 'product_cat'].unique(), ['Total'])
                for p in PRODUCTS}

WORLD = pd.read_parquet(HERE / 'data' / 'world_patches.parquet')
WORLD['xs'] = WORLD['xs'].map(list)
WORLD['ys'] = WORLD['ys'].map(list)

# ---------------------------------------------------------------- map
map_src = ColumnDataSource(dict(
    xs=list(WORLD['xs']), ys=list(WORLD['ys']),
    iso3=list(WORLD['iso3']), name=list(WORLD['name']),
    hovname=list(WORLD['name']), value=[np.nan] * len(WORLD)))

# Region membership by map patch (Region dropdown highlights the members).
REGION_MEMBER_IDX = {}
for _j, _iso in enumerate(WORLD['iso3']):
    _r = REGION_OF.get(_iso)
    if _r:
        REGION_MEMBER_IDX.setdefault(_r, []).append(_j)

# Linear (not log) — Trade balance can be negative and units vary in scale.
color_mapper = LinearColorMapper(palette=PALETTE, low=0.0, high=1.0, nan_color='#e8e8e3')

mp = figure(width=CHART_W, height=CHART_H, match_aspect=True,
            x_range=(-170, 190), y_range=(-58, 85),
            tools=['pan', 'wheel_zoom', 'box_zoom', 'reset', 'tap', SaveTool()],
            active_scroll='wheel_zoom',
            toolbar_location='right', background_fill_color=PANEL_BG,
            border_fill_color='white', outline_line_color=None)
mp.grid.visible = False
mp.axis.visible = False
patches = mp.patches('xs', 'ys', source=map_src,
                     fill_color={'field': 'value', 'transform': color_mapper},
                     line_color='white', line_width=0.4,
                     hover_fill_color={'field': 'value', 'transform': color_mapper},
                     hover_line_color=BRAND, hover_line_width=1.5,
                     selection_line_color=BRAND, selection_line_width=1.5,
                     nonselection_fill_alpha=1.0, nonselection_line_alpha=1.0)
mp.add_tools(HoverTool(renderers=[patches],
                       tooltips=[('', '@hovname'), ('value', '@value{0,0.000}')]))
cbar = ColorBar(color_mapper=color_mapper, title='USD bn', width=12,
                title_text_font=FONT, major_label_text_font=FONT,
                title_text_color=BRAND, background_fill_alpha=0)
mp.add_layout(cbar, 'right')

bg_map_src = ColumnDataSource(dict(
    url=[BACKGROUND_URL], x=[mp.x_range.start], y=[mp.y_range.start],
    w=[mp.x_range.end - mp.x_range.start], h=[mp.y_range.end - mp.y_range.start]))
mp.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_map_src,
             anchor='bottom_left', global_alpha=0.18, level='underlay')
mp.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=WATERMARK,
                    text_font=FONT, text_font_style='bold', text_font_size='0.875em',
                    text_color='#556B2F', text_alpha=0.8))

# ---------------------------------------------------------------- line (up to 4 series)
ALL_DATES = [pd.Timestamp(d) for d in np.sort(DATA['Date'].unique())]
line_src = ColumnDataSource(dict({'date': ALL_DATES},
                                 **{f's{i}': [np.nan] * len(ALL_DATES) for i in range(MAX_SERIES)}))

line_xr = DataRange1d(only_visible=True, range_padding=0.02)
line_yr = DataRange1d(only_visible=True, range_padding=0.08)
ln = figure(width=CHART_W, height=CHART_H, x_axis_type='datetime',
            x_range=line_xr, y_range=line_yr,
            tools=['pan', 'xwheel_zoom', 'box_zoom', 'reset', SaveTool()],
            active_scroll='xwheel_zoom', toolbar_location='right',
            background_fill_color=PANEL_BG, border_fill_color='white',
            outline_line_color=None)
ln.xgrid.visible = False
ln.ygrid.grid_line_color = 'rgba(85,107,47,0.12)'
ln.title.text = 'China trade'

line_renderers = []
for i in range(MAX_SERIES):
    r = ln.line('date', f's{i}', source=line_src, name=f's{i}',
                color=SERIES_COLORS[i], line_width=3, alpha=0.85)
    r.visible = False
    line_renderers.append(r)
line_xr.renderers = line_renderers
line_yr.renderers = line_renderers

ln.add_layout(Span(location=0, dimension='width', line_color='#999999', line_width=1))

right_axis = LinearAxis()
right_axis.formatter = NumeralTickFormatter(format='0,0.0')
ln.add_layout(right_axis, 'right')

ln.yaxis.axis_label = ''
ln.yaxis.formatter = NumeralTickFormatter(format='0,0.0')
ln.xaxis.formatter = DatetimeTickFormatter(months='%b %Y')
for ax in (ln.yaxis, right_axis, ln.xaxis):
    ax.axis_label_text_font = FONT
    ax.axis_label_text_font_size = '18px'
    ax.major_label_text_font = FONT
    ax.major_label_text_font_size = '20px'

ln.add_tools(HoverTool(renderers=line_renderers, mode='mouse',
                       tooltips=[('', '$name'), ('', '$y{0,0.000}'), ('', '$x{%b %Y}')],
                       formatters={'$x': 'datetime'}))

legend = Legend(items=[], location='top_left', orientation='vertical',
                label_text_font=FONT, label_text_font_size='14px', background_fill_alpha=0.7)
ln.add_layout(legend)

bg_line_src = ColumnDataSource(dict(url=[BACKGROUND_URL], x=[0], y=[0], w=[1], h=[1]))
ln.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_line_src,
             anchor='bottom_left', global_alpha=0.12, level='underlay')
ln.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=WATERMARK,
                    text_font=FONT, text_font_style='bold', text_font_size='0.875em',
                    text_color='#556B2F', text_alpha=0.8))

# ---------------------------------------------------------------- data table + CSV
# Formatting mirrors cn_auto_exports: Georgia, bold green header, zebra rows, 2-dp / "N/A",
# %Y-%m-%d dates, 200/150 col widths, last-24-rows table. The table reads `table_src` (24 rows);
# the CSV button is pure client-side JS over `csv_src` (full history) — no server round-trip.
DATE_WIDTH, VAL_WIDTH = 200, 150
cell_fmt = HTMLTemplateFormatter(template="""
<style>
  .slick-column-name {font-family: Georgia; font-weight: 900; font-size: 0.9rem;}
  .slick-header-column {background-color: hsla(120, 100%, 25%, 0.1) !important;}
  .slick-cell {font-family: Georgia; font-size: 0.9rem;}
  .slick-row:nth-of-type(even) {background-color: hsla(120, 100%, 25%, 0.1) !important;}
</style>
<%= (value != null) ? value.toFixed(2) : "N/A" %>
""")

table_src = ColumnDataSource(dict({'date': []},                 # last 24 rows (display)
                                  **{f's{i}': [] for i in range(MAX_SERIES)}))
csv_src = ColumnDataSource(dict({'date': []},                   # full history (download)
                                **{f's{i}': [] for i in range(MAX_SERIES)}))
date_col = TableColumn(field='date', title='Date', width=DATE_WIDTH)
data_table = DataTable(source=table_src, columns=[date_col], width=DATE_WIDTH,
                       height=320, index_position=None, header_row=True)

download_btn = Button(label='Download CSV', width=130, height=31, align='end')
download_btn.js_on_click(CustomJS(args=dict(source=csv_src, table=data_table), code="""
    const cols = table.columns, data = source.data;
    const fields = cols.map(c => c.field);
    const q = s => '"' + String(s).replace(/"/g, '""') + '"';     // labels contain commas
    const n = (data['date'] || []).length;
    const lines = [cols.map(c => q(c.title)).join(',')];
    for (let r = 0; r < n; r++) {
        const row = fields.map(f => {
            const v = data[f][r];
            if (f === 'date') return v;                            // already 'YYYY-MM-DD'
            return (v === null || v === undefined || Number.isNaN(v)) ? '' : v;
        });
        lines.push(row.join(','));
    }
    const blob = new Blob([lines.join('\\n')], {type: 'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'china_trade.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
"""))
table_title = Div(text='<b>Data</b>',
                  styles={'font-family': FONT, 'font-size': '14px', 'color': BRAND})

# ---------------------------------------------------------------- styling pass
for f in (mp, ln):
    f.title.text_font = FONT
    f.title.text_font_style = 'bold'
    f.title.text_font_size = '25px'
    f.axis.axis_label_text_font = FONT
    f.axis.major_label_text_font = FONT

# ---------------------------------------------------------------- controls
flow_sel = Select(title='Flow', value='Exports', options=FLOWS, width=130)
product_sel = Select(title='Product', value='Total', options=PRODUCTS, width=150)
pcat_sel = Select(title='Product category', value='Total', options=PRODUCT_CATS['Total'], width=190)
unit_sel = Select(title='Unit', value='USD bn', options=UNITS, width=120)
add_btn = Button(label='Add to chart', button_type='primary', width=130, height=31, align='end')
world_btn = Button(label='World', width=110, height=31, align='end')
ISO_IDX = {iso: j for j, iso in enumerate(WORLD['iso3'])}
COUNTRY_ISO = dict(zip(WORLD['name'], WORLD['iso3']))
country_sel = Select(title='Country', value='Map', options=['Map'] + sorted(WORLD['name']), width=200)
region_sel = Select(title='Region', value='Map', options=['Map'] + REGION_LABELS, width=180)
partner_label = Div(text='<b>Partner economy</b>',
                    styles={'font-family': FONT, 'font-size': '13px', 'font-weight': 'bold'})
report_label = Div(text='<b>Reporting economy: China</b>',
                   styles={'font-family': FONT, 'font-size': '13px', 'font-weight': 'bold'})
map_instr = Div(text='<i>China is the reporter. Choose Flow / Product / Category / Unit, pick a '
                     'partner (click the map, or Country / Region / World), then “Add to chart”.</i>',
                styles={'font-family': FONT, 'font-size': '12px', 'color': '#555'})
series_sel = Select(title='Series on chart (select to remove)', options=[], width=560)
remove_btn = Button(label='Remove', width=90, height=31, align='end')
clear_btn = Button(label='Clear all', width=90, height=31, align='end')

STATE = {'iso3': None, 'country': None}
SERIES = []
_busy = {'v': False}

def _series_values(s):
    key = (s['flow'], s['product'], s['product_cat'], s['unit'], s['iso3'])
    try:
        sub = IDX.loc[key]
    except KeyError:
        return [np.nan] * len(ALL_DATES)
    if isinstance(sub, pd.Series):                      # single matching row
        v = pd.Series({sub['Date']: sub['value']})
    else:
        v = sub.groupby('Date')['value'].sum(min_count=1)
    return [float(v.get(d)) if d in v.index else np.nan for d in ALL_DATES]

def rebuild_chart():
    data = {'date': ALL_DATES}
    items = []
    for i in range(MAX_SERIES):
        col = f's{i}'
        if i < len(SERIES):
            data[col] = _series_values(SERIES[i])
            line_renderers[i].visible = True
            items.append(LegendItem(label={'value': SERIES[i]['label']}, renderers=[line_renderers[i]]))
        else:
            data[col] = [np.nan] * len(ALL_DATES)
            line_renderers[i].visible = False
    line_src.data = data
    legend.items = items
    series_sel.options = [s['label'] for s in SERIES]

    # Table/CSV: wide layout (Date + one column per active series), dropping all-empty rows.
    active = [f's{i}' for i in range(len(SERIES))]
    tdf = pd.DataFrame({'date': ALL_DATES, **{c: data[c] for c in active}})
    tdf = tdf.dropna(subset=active, how='all') if active else tdf.iloc[0:0]

    def _cds(df):
        out = {'date': [pd.Timestamp(d).strftime('%Y-%m-%d') for d in df['date']]}
        for c in active:
            out[c] = df[c].tolist()
        return out

    csv_src.data = _cds(tdf)                 # full history (download)
    table_src.data = _cds(tdf.tail(24))      # last 24 rows (display), matching cn_auto_exports
    cols = [date_col]
    for i in range(len(SERIES)):
        cols.append(TableColumn(field=f's{i}', title=SERIES[i]['label'],
                                formatter=cell_fmt, width=VAL_WIDTH))
    data_table.columns = cols
    data_table.width = DATE_WIDTH + len(SERIES) * VAL_WIDTH if SERIES else DATE_WIDTH

def add_series():
    if STATE['iso3'] is None or len(SERIES) >= MAX_SERIES:
        return
    s = dict(country=STATE['country'], iso3=STATE['iso3'], flow=flow_sel.value,
             product=product_sel.value, product_cat=pcat_sel.value, unit=unit_sel.value)
    s['label'] = (f"China, {s['flow']}, {s['country']}, "
                  f"{s['product']}/{s['product_cat']}, {s['unit']}")
    if any(x['label'] == s['label'] for x in SERIES):
        return
    SERIES.append(s)
    rebuild_chart()

def remove_series():
    if series_sel.value:
        SERIES[:] = [s for s in SERIES if s['label'] != series_sel.value]
        rebuild_chart()

def clear_series():
    SERIES.clear()
    rebuild_chart()

def refresh_map():
    # Colour the map by the current Flow / Product / Category / Unit, at that selection's latest
    # month (different products/units end at different dates). Linear scale (Trade balance < 0).
    flow, prod, pcat, unit = flow_sel.value, product_sel.value, pcat_sel.value, unit_sel.value
    try:
        sub = IDX.loc[(flow, prod, pcat, unit)]        # all iso3 for this combo (index = iso3)
    except KeyError:
        sub = None
    if sub is None or len(sub) == 0:
        map_src.data['value'] = [np.nan] * len(map_src.data['iso3'])
        mp.title.text = f'China, {flow}, {prod}/{pcat}, {unit} — no data'
        return
    edate = sub['Date'].max()
    by_iso = sub[sub['Date'] == edate].groupby(level=0, observed=True)['value'].sum()
    vals = [by_iso.get(i, np.nan) for i in map_src.data['iso3']]
    map_src.data['value'] = vals
    finite = [v for v in vals if v == v]
    if finite:
        lo, hi = min(finite), max(finite)
        color_mapper.low, color_mapper.high = (lo, hi) if lo != hi else (lo, lo + 1)
    cbar.title = unit
    mp.title.text = f'China, {flow}, {prod}/{pcat}, {unit}, {edate:%b %Y}'

def on_tap(attr, old, new):
    if _busy['v']:
        return
    if new:
        i = new[0]
        iso, name = map_src.data['iso3'][i], map_src.data['name'][i]
        STATE['iso3'], STATE['country'] = iso, name
        _busy['v'] = True
        country_sel.value = name if name in COUNTRY_ISO else 'Map'
        region_sel.value = 'Map'
        _busy['v'] = False
    else:
        STATE['iso3'] = STATE['country'] = None

def pick_country(attr, old, new):
    if _busy['v'] or new == 'Map':
        return
    iso = COUNTRY_ISO[new]
    STATE['iso3'], STATE['country'] = iso, new
    _busy['v'] = True
    map_src.selected.indices = [ISO_IDX[iso]] if iso in ISO_IDX else []
    region_sel.value = 'Map'
    _busy['v'] = False

def use_world():
    _busy['v'] = True
    map_src.selected.indices = []
    country_sel.value = 'Map'
    region_sel.value = 'Map'
    _busy['v'] = False
    STATE['iso3'], STATE['country'] = 'WLD', 'World'

def pick_region(attr, old, new):
    if _busy['v'] or new == 'Map':
        return
    _busy['v'] = True
    map_src.selected.indices = REGION_MEMBER_IDX.get(new, [])
    country_sel.value = 'Map'
    _busy['v'] = False
    STATE['iso3'], STATE['country'] = REGION_ISO[new], new

def on_product_change(attr, old, new):
    opts = PRODUCT_CATS.get(new, ['Total'])
    pcat_sel.options = opts
    if pcat_sel.value not in opts:
        pcat_sel.value = 'Total' if 'Total' in opts else opts[0]
    refresh_map()

map_src.selected.on_change('indices', on_tap)
add_btn.on_click(add_series)
world_btn.on_click(use_world)
country_sel.on_change('value', pick_country)
region_sel.on_change('value', pick_region)
remove_btn.on_click(remove_series)
clear_btn.on_click(clear_series)
product_sel.on_change('value', on_product_change)
flow_sel.on_change('value', lambda a, o, n: refresh_map())
pcat_sel.on_change('value', lambda a, o, n: refresh_map())
unit_sel.on_change('value', lambda a, o, n: refresh_map())

def _sync_bg(fig, src):
    def _cb(attr, old, new):
        src.data.update(x=[fig.x_range.start], y=[fig.y_range.start],
                        w=[fig.x_range.end - fig.x_range.start],
                        h=[fig.y_range.end - fig.y_range.start])
    return _cb

for _fig, _src in ((mp, bg_map_src), (ln, bg_line_src)):
    _cb = _sync_bg(_fig, _src)
    for _rng in (_fig.x_range, _fig.y_range):
        _rng.on_change('start', _cb)
        _rng.on_change('end', _cb)

# ---------------------------------------------------------------- layout
header = Div(text='<h2 style="font-family:Georgia;color:#556B2F;border-bottom:2px solid '
                  '#104b1f;padding-bottom:6px;margin-bottom:4px;">China trade — by partner</h2>',
             sizing_mode='stretch_width')
footer = Div(text='<div style="font-family:Georgia;font-size:12px;color:#333;border-top:'
                  f'1px solid #104b1f;padding-top:6px;">Source: EAE, China Customs. Latest: '
                  f'{CUR:%b %Y}.  <a href="https://www.eastasiaecon.com" '
                  'style="color:#556B2F;font-weight:bold;text-decoration:none;">'
                  'www.eastasiaecon.com</a></div>', sizing_mode='stretch_width')

del DATA   # only IDX (+ the precomputed option lists) are used at runtime; free the copy
refresh_map(); rebuild_chart()
curdoc().add_root(column(header,
                         report_label,
                         column(partner_label, row(country_sel, region_sel, world_btn)),
                         row(flow_sel, product_sel, pcat_sel, unit_sel, add_btn),
                         row(series_sel, remove_btn, clear_btn, download_btn),
                         map_instr,
                         row(mp, ln),
                         table_title,
                         data_table,
                         footer, sizing_mode='stretch_width'))
curdoc().title = 'China trade — by partner'
