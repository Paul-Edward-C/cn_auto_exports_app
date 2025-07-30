import geopandas as gpd
import pandas as pd
import numpy as np
import difflib
import os
import matplotlib.colors as mcolors
import re

from bokeh.io import curdoc
from bokeh.models import (
    GeoJSONDataSource, Select, Button, ColumnDataSource, HoverTool, Div,Label,NumeralTickFormatter, DatetimeTickFormatter,
    DataTable, TableColumn, HTMLTemplateFormatter, ColorBar, LinearColorMapper, NumberFormatter, CustomJS
)


from bokeh.plotting import figure
from bokeh.layouts import column, row
from bokeh.themes import Theme

# --- Theme settings ---
theme_json = {
    'attrs': {
        'figure': {
            'background_fill_color': '#228B22',
            'background_fill_alpha': 0.05,
        },
        'Axis': {
            'axis_label_text_font': 'Georgia',
            'major_label_text_font': 'Georgia',
        },
        'Title': {
            'text_font_style': 'bold',
            'text_font': 'Georgia',
            'text_font_size': '18px',
        },
        'Legend': {
            'label_text_font': 'Georgia',
            'padding': 1,
            'spacing': 1,
            'background_fill_alpha': 0.7,
        },
    }
}

curdoc().theme = Theme(json=theme_json)

# --- 1. Palette ---
blues = [
    "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"
]
greens = [
    "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"
]
palette = blues[::-1] + greens
def interpolate_palette(palette, n):
    cmap = mcolors.LinearSegmentedColormap.from_list('custom', palette)
    return [mcolors.to_hex(cmap(i/(n-1))) for i in range(n)]
smooth_palette = interpolate_palette(palette, 50)

formatter = HTMLTemplateFormatter(
    template="""
    <style>
        .slick-column-name {font-family: Georgia; font-weight: 900; font-size: 0.9rem;}
        .slick-header-column {background-color: hsla(120, 100%, 25%, 0.1) !important;}
        .slick-cell {font-family: Georgia; font-size: 0.9rem;}
        .slick-row:nth-of-type(even) {background-color: hsla(120, 100%, 25%, 0.1) !important;}
    </style>
    <%= (value != null) ? value.toFixed(1) : "N/A" %>
    """
)

# --- 2. Load map and data ---
world = gpd.read_file('app/data/ne_10m_admin_0_countries.shp')
df = pd.read_csv('app/data/auto_total.csv')

# --- Find the date column right after loading df ---
date_col = None
for col in df.columns:
    if re.search('date', col, re.IGNORECASE):
        date_col = col
        break

if date_col is not None:
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

# --- 3. Map country names to DataFrame columns ---
country_type_value_to_col = {}
export_types = set()
value_types = set()
for col in df.columns:
    m1 = re.match(r'Exports, Autos, (\w+), (.*?), USD m', col)
    m2 = re.match(r'Exports, Autos, (\w+), (.*?), % of total', col)
    if m1:
        exp_type = m1.group(1)
        country = m1.group(2)
        export_types.add(exp_type)
        value_types.add('USD m')
        if country not in country_type_value_to_col:
            country_type_value_to_col[country] = {}
        if exp_type not in country_type_value_to_col[country]:
            country_type_value_to_col[country][exp_type] = {}
        country_type_value_to_col[country][exp_type]['USD m'] = col
    elif m2:
        exp_type = m2.group(1)
        country = m2.group(2)
        export_types.add(exp_type)
        value_types.add('% of total')
        if country not in country_type_value_to_col:
            country_type_value_to_col[country] = {}
        if exp_type not in country_type_value_to_col[country]:
            country_type_value_to_col[country][exp_type] = {}
        country_type_value_to_col[country][exp_type]['% of total'] = col

country_list = list(country_type_value_to_col.keys())
export_types = sorted(list(export_types))
value_types = sorted(list(value_types))

world_country = 'World'
world_chart_source = ColumnDataSource(data=dict(date=[], value=[]))

def get_world_timeseries(export_type, value_type):
    world_col = country_type_value_to_col.get(world_country, {}).get(export_type, {}).get(value_type)
    if world_col and world_col in df.columns:
        if date_col and date_col in df.columns:
            dates = df[date_col].tolist()
        else:
            dates = df.index.tolist()
        values = df[world_col].apply(lambda x: round(x,1) if pd.notnull(x) else None).tolist()
        return dict(date=dates, value=values)
    else:
        return dict(date=[], value=[])

def update_world_chart():
    export_type = select_type.value
    value_type = select_value_type.value
    new_data = get_world_timeseries(export_type, value_type)
    world_line_chart.title.text = f"World Monthly Auto Exports ({export_type}, {value_type})"
    world_chart_source.data = new_data

def has_match(admin_name):
    match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
    return bool(match)

filtered_world = world[world['ADMIN'].apply(has_match)].reset_index(drop=True)

admin_to_df_map = {}
for admin_name in filtered_world['ADMIN']:
    match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
    if match:
        admin_to_df_map[admin_name] = match[0]
    else:
        admin_to_df_map[admin_name] = None

# --- 4. Ensure China is present ---
if not (filtered_world["ADMIN"] == "China").any():
    china_row = world[world["ADMIN"] == "China"]
    filtered_world = pd.concat([filtered_world, china_row], ignore_index=True)

# --- 5. Prepare values ---
default_type = "Total"
default_value_type = "USD m"

latest_row = df.iloc[-1]
country_exports = {}
for admin_name, df_country in admin_to_df_map.items():
    df_col = country_type_value_to_col.get(df_country, {}).get(default_type, {}).get(default_value_type)
    if df_col and df_col in df.columns:
        country_exports[admin_name] = latest_row[df_col]
    else:
        country_exports[admin_name] = None

filtered_world["exports"] = filtered_world["ADMIN"].map(country_exports)
if default_value_type == 'USD m':
    filtered_world["exports_log"] = filtered_world["exports"].apply(
        lambda x: np.log1p(x) if pd.notnull(x) and x > 0 else None
    )
else:
    filtered_world["exports_log"] = filtered_world["exports"]
filtered_world["note"] = filtered_world["exports"].apply(
    lambda x: "No Data" if pd.isnull(x) else ""
)
filtered_world.loc[filtered_world["ADMIN"] == "China", "note"] = "Exporter (no data)"

# --- 6. Apply color mapping ---
def get_colors(export_values, palette, vmin, vmax, highlight_admins=None):
    export_values = np.array(export_values, dtype=float)
    norm = (export_values - vmin) / (vmax - vmin) if (vmax - vmin) != 0 else np.zeros_like(export_values)
    norm = np.clip(norm, 0, 1)
    idx = (norm * (len(palette)-1)).round().astype(int)
    colors = []
    for admin, v, i in zip(filtered_world["ADMIN"], export_values, idx):
        if np.isnan(v):
            colors.append("#dddddd")
        elif highlight_admins is not None and admin not in highlight_admins:
            colors.append("#dddddd")
        else:
            colors.append(palette[i])
    return colors

exports_log_min = filtered_world["exports_log"].min()
exports_log_max = filtered_world["exports_log"].max()
exports_log = filtered_world["exports_log"].values
filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)

columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
filtered_world_small = filtered_world[columns_to_keep]
geo_source = GeoJSONDataSource(geojson=filtered_world_small.to_json())

# --- 7. Bokeh plot ---
TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"
p = figure(
    title=f"China, Auto exports by country, {default_type}, {default_value_type}",
    tools=TOOLS,
    x_axis_location=None, y_axis_location=None,
    active_scroll='wheel_zoom',
    width=950, height=520,
)
p.grid.grid_line_color = None

color_mapper_obj = LinearColorMapper(palette=smooth_palette, low=exports_log_min, high=exports_log_max, nan_color="#dddddd")
color_bar = ColorBar(color_mapper=color_mapper_obj, label_standoff=12, location=(0,0),
                     title=f"Exports {default_type}, {default_value_type}")
p.add_layout(color_bar, 'right')

p.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen',
                    text=f"www.eastasiaecon.com/cn/#charts"))

p.xaxis.axis_label = f'Source: CCA, EEA'

patches = p.patches(
    'xs', 'ys', source=geo_source,
    fill_color='custom_color',
    fill_alpha=0.7,
    line_color="gray", line_width=0.5
)

hover = p.select_one(HoverTool)
hover.point_policy = "follow_mouse"
hover.tooltips = [
    ("Country", "@ADMIN"),
    (f"Exports ({default_value_type})", "@exports{0,0.0}"),
    ("Note", "@note")
]

select_country = Select(title="Select Country", value="", options=sorted(list(admin_to_df_map.keys())), width=220)
select_type = Select(title="Export Type", value=default_type, options=export_types, width=220)
select_value_type = Select(title="Value Type", value=default_value_type, options=value_types, width=220)

top15_button = Button(label="Highlight Top 15", button_type="success", width=220, height=35)
top15_button.css_classes = ["styled-btn"]

reset_button = Button(
    label="🔄",
    button_type="default",
    width=40,
    height=35,
    css_classes=["styled-btn", "reset-btn"]
)

country_width = 250
date_width = 200
cat_width = 350

top_15_width = country_width + cat_width
total_width = date_width + cat_width

top15_table_source = ColumnDataSource(data=dict(country=[], value=[]))
top15_table = DataTable(
    source=top15_table_source,
    columns=[
        TableColumn(field="country", title="Country", width=country_width),
        TableColumn(field="value", title=f"Exports ({default_type}, {default_value_type})", width=cat_width, formatter=formatter)
    ],
    width=top_15_width,
    height=350,
    index_position=None,
)

top15_chart_source = ColumnDataSource(data=dict(country=[], value=[]))
top15_chart = figure(
    x_range=[], height=350, width=370, title=f"Top 15 destinations, {default_type}, {default_value_type}", toolbar_location=None, tools="",
    min_border_left=10, min_border_right=10, min_border_top=10, min_border_bottom=10
)
top15_chart.vbar(x="country", top="value", source=top15_chart_source, width=0.7, color="#556B2F", alpha=0.7)
top15_chart.xaxis.major_label_orientation = 1.0
top15_chart.xgrid.grid_line_color = None
top15_chart.title.text_font_size = "14px"

selected_table_source = ColumnDataSource(data=dict(index=[], date=[], exports=[]))

# --- After your other chart/table setup ---
world_line_chart = figure(
    height=220, width=600,
    title="Monthly World Auto Exports",
    x_axis_type="auto", tools="pan,xwheel_zoom,box_zoom,reset,save",
    margin=(20, 10, 10, 10)
)
world_line_chart.line(x="date", y="value", source=world_chart_source, line_width=2, color="#2171b5")
world_line_chart.yaxis.formatter = NumeralTickFormatter(format="0,0.0")
world_line_chart.xaxis.formatter = DatetimeTickFormatter(years="%b-%y", months="%b-%y")

update_world_chart()    # <-- Ensures chart is populated at startup

def reset_top15():
    exports_log_min = filtered_world["exports_log"].min()
    exports_log_max = filtered_world["exports_log"].max()
    exports_log = filtered_world["exports_log"].values
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)
    columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    filtered_world_small = filtered_world[columns_to_keep]
    geo_source.geojson = filtered_world_small.to_json()
    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []

reset_button.on_click(reset_top15)

def make_data_table_columns(export_type, value_type):
    return [
        TableColumn(field="date", title="Date", width=date_width),
        TableColumn(field="exports", title=f"Exports ({export_type}, {value_type})", formatter=formatter, width=cat_width)
    ]

columns = make_data_table_columns(default_type, default_value_type)
data_table = DataTable(source=selected_table_source, columns=columns, width=total_width, height=400, index_position=None, header_row=True)

def update_selected(attr, old, new):
    country = select_country.value
    exp_type = select_type.value
    value_type = select_value_type.value
    df_country = admin_to_df_map.get(country)
    df_col = country_type_value_to_col.get(df_country, {}).get(exp_type, {}).get(value_type)
    if df_col and df_col in df.columns:
        last_24 = df.tail(24)
        if date_col and date_col in df.columns:
            dates = last_24[date_col].dt.strftime('%y-%b-%d').tolist()
        else:
            dates = last_24[date_col].dt.strftime('%y-%b-%d').tolist()
        exports = last_24[df_col].apply(lambda x: round(x, 1) if pd.notnull(x) else None).tolist()
        selected_table_source.data = dict(
            index=list(range(len(dates))),
            date=dates,
            exports=exports
        )
    else:
        selected_table_source.data = dict(index=[], date=[], exports=[])

select_country.on_change('value', update_selected)
select_type.on_change('value', update_selected)
select_value_type.on_change('value', update_selected)

selected_div = Div(text="")
def update_div(attr, old, new):
    if selected_table_source.data['exports']:
        latest_export = selected_table_source.data['exports'][-1]
        country = select_country.value
        exp_type = select_type.value
        value_type = select_value_type.value
        latest_val = f"{latest_export:.1f}" if latest_export is not None else 'N/A'
        selected_div.text = f"<h2>{country}, {exp_type}, {value_type}</h2><p>Latest Exports: {latest_val}</p>"
    else:
        selected_div.text = ""

def update_map_type(attr, old, new):
    exp_type = select_type.value
    value_type = select_value_type.value
    country_exports = {}
    for admin_name, df_country in admin_to_df_map.items():
        df_col = country_type_value_to_col.get(df_country, {}).get(exp_type, {}).get(value_type)
        if df_col and df_col in df.columns:
            country_exports[admin_name] = latest_row[df_col]
        else:
            country_exports[admin_name] = None
    filtered_world["exports"] = filtered_world["ADMIN"].map(country_exports)
    if value_type == "USD m":
        filtered_world["exports_log"] = filtered_world["exports"].apply(
            lambda x: np.log1p(x) if pd.notnull(x) and x > 0 else None
        )
    else:
        filtered_world["exports_log"] = filtered_world["exports"]
    filtered_world["note"] = filtered_world["exports"].apply(
        lambda x: "No Data" if pd.isnull(x) else ""
    )
    filtered_world.loc[filtered_world["ADMIN"] == "China", "note"] = "Exporter (no data)"
    exports_log_min = filtered_world["exports_log"].min()
    exports_log_max = filtered_world["exports_log"].max()
    exports_log = filtered_world["exports_log"].values
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)
    columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    filtered_world_small = filtered_world[columns_to_keep]
    geo_source.geojson = filtered_world_small.to_json()

    p.title.text = f"Automobile Exports by Country ({exp_type}, {value_type})"
    data_table.columns = make_data_table_columns(exp_type, value_type)
    color_mapper_obj.low = exports_log_min
    color_mapper_obj.high = exports_log_max
    color_bar.title = f"Exports ({exp_type}, {value_type})"
    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []

    update_world_chart()  # <-- Ensures World chart updates on menu change

# --- Highlight Top 15: ONLY top 15 get palette, ALL others (including China) are grey ---
def highlight_top15():
    exp_type = select_type.value
    value_type = select_value_type.value

    country_exports = {}
    for admin_name, df_country in admin_to_df_map.items():
        df_col = country_type_value_to_col.get(df_country, {}).get(exp_type, {}).get(value_type)
        if df_col and df_col in df.columns:
            country_exports[admin_name] = latest_row[df_col]
        else:
            country_exports[admin_name] = None

    filtered_world["exports"] = filtered_world["ADMIN"].map(country_exports)
    if value_type == "USD m":
        exports_log = np.log1p(filtered_world["exports"].values.astype(float))
        exports_log[np.isnan(exports_log)] = np.nan
        filtered_world["exports_log"] = exports_log
    else:
        filtered_world["exports_log"] = filtered_world["exports"]

    exports_log = filtered_world["exports_log"].values
    valid_indices = np.where(~np.isnan(exports_log))[0]
    if len(valid_indices) > 15:
        top15_idx = valid_indices[np.argpartition(-exports_log[valid_indices], 15)[:15]]
    else:
        top15_idx = valid_indices
    top_admins = set(filtered_world.iloc[top15_idx]["ADMIN"].values)
    
    colors = np.full(filtered_world.shape[0], "#dddddd", dtype=object)
    if len(top15_idx) > 0:
        exports_log_min = exports_log[top15_idx].min()
        exports_log_max = exports_log[top15_idx].max()
        norm = (exports_log[top15_idx] - exports_log_min) / (exports_log_max - exports_log_min) if exports_log_max != exports_log_min else np.zeros(len(top15_idx))
        idx = (norm * (len(smooth_palette) - 1)).round().astype(int)
        for i, ci in enumerate(top15_idx):
            colors[ci] = smooth_palette[idx[i]]

    filtered_world["custom_color"] = colors

    columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    filtered_world_small = filtered_world[columns_to_keep]
    geo_source.geojson = filtered_world_small.to_json()

    top15_data = filtered_world.iloc[top15_idx][["ADMIN", "exports"]].sort_values("exports", ascending=False)
    top15_table_source.data = dict(
        country=top15_data["ADMIN"].tolist(),
        value=top15_data["exports"].tolist(),
    )
    top15_chart_source.data = dict(
        country=top15_data["ADMIN"].tolist(),
        value=top15_data["exports"].tolist(),
    )
    top15_chart.x_range.factors = top15_data["ADMIN"].tolist()

top15_button.on_click(highlight_top15)

# --- Download buttons ---
download_timeseries_button = Button(label="Download Timeseries CSV", button_type="primary", width=220, height=35)
download_top15_button = Button(label="Download Top 15 CSV", button_type="primary", width=220, height=35)

download_timeseries_button.js_on_click(CustomJS(args=dict(source=selected_table_source), code="""
    function toCSV(data) {
        const cols = Object.keys(data);
        const nrows = data[cols[0]].length;
        const lines = [cols.join(",")];
        for (let i = 0; i < nrows; i++) {
            lines.push(cols.map(col => 
                (data[col][i] == null ? "" : `"${data[col][i]}"`)
            ).join(","));
        }
        return lines.join("\\n");
    }
    const csv = toCSV(source.data);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "timeseries.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
"""))

download_top15_button.js_on_click(CustomJS(args=dict(source=top15_table_source), code="""
    function toCSV(data) {
        const cols = Object.keys(data);
        const nrows = data[cols[0]].length;
        const lines = [cols.join(",")];
        for (let i = 0; i < nrows; i++) {
            lines.push(cols.map(col => 
                (data[col][i] == null ? "" : `"${data[col][i]}"`)
            ).join(","));
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

style = """
<style>
.bk-btn.styled-btn {
    font-size: 0.9rem !important;
    font-family: Georgia !important;
    border: none !important;
    border-radius: 5px !important;
    background: #104b1f !important;
    color: white !important;
    transition: opacity .2s ease-in-out !important;
    height: 35px !important;
    width: 220px !important;
    margin: 0 !important;
    padding: 0px 10px !important;
    box-shadow: none !important;
}
</style>
"""
style_div = Div(text=style)

select_type = Select(title="Export Type", value=default_type, options=export_types, width=220)
select_value_type = Select(title="Value Type", value=default_value_type, options=value_types, width=220)
select_country = Select(title="Select Country", value="", options=sorted(list(admin_to_df_map.keys())), width=220)

top_selectors_row = row(
    select_type,
    select_value_type,
    sizing_mode="fixed"
)
bottom_selector_row = row(
    select_country,
    download_timeseries_button,
    sizing_mode="fixed"
)
top15_buttons_row = row(
    top15_button,
    reset_button,
    download_top15_button,
    sizing_mode="fixed"
)

top15_col = column(
    top15_buttons_row,
    top15_chart,
    top15_table,
    sizing_mode="fixed",
    width=370
)
main_row = row(
    p,
    top15_col,
    sizing_mode="stretch_width",
    height=520
)

layout = column(
    style_div,
    top_selectors_row,
    world_line_chart,
    main_row,
    bottom_selector_row,
    selected_div,
    data_table,
    sizing_mode="stretch_width"
)
curdoc().add_root(layout)

def update_titles_and_map(attr, old, new):
    exp_type = select_type.value
    value_type = select_value_type.value
    p.title.text = f"Automobile Exports by Country ({exp_type}, {value_type})"
    top15_chart.title.text = f"Top 15 destinations, {exp_type}, {value_type}"
    color_bar.title = f"Exports ({exp_type}, {value_type})"
    data_table.columns = make_data_table_columns(exp_type, value_type)
    top15_table.columns = [
        TableColumn(field="country", title="Country", width=200),
        TableColumn(field="value", title=f"Exports ({exp_type}, {value_type})", width=150, formatter=formatter)
    ]
    update_map_type(attr, old, new)
    update_world_chart()

select_type.on_change('value', update_titles_and_map)
select_value_type.on_change('value', update_titles_and_map)
select_country.on_change('value', update_selected)
select_type.on_change('value', update_selected)
select_value_type.on_change('value', update_selected)

curdoc().title = "China, Auto Exports"