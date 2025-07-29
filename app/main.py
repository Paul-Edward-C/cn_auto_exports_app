import geopandas as gpd
import pandas as pd
import numpy as np
import difflib
import os
import matplotlib.colors as mcolors
import re

from bokeh.io import curdoc
from bokeh.models import (
    GeoJSONDataSource, Select, Button, ColumnDataSource, HoverTool, Div,
    DataTable, TableColumn, HTMLTemplateFormatter, ColorBar, LinearColorMapper, NumberFormatter
)
from bokeh.plotting import figure
from bokeh.layouts import column, row

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
china_color = "#dddddd"

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
default_type = export_types[0]
default_value_type = value_types[0]
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
        elif highlight_admins is not None and admin not in highlight_admins and admin != "China":
            colors.append("#dddddd")
        else:
            colors.append(palette[i])
    return colors

exports_log_min = filtered_world["exports_log"].min()
exports_log_max = filtered_world["exports_log"].max()
exports_log = filtered_world["exports_log"].values
filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)
filtered_world.loc[filtered_world["ADMIN"] == "China", "custom_color"] = china_color

geo_source = GeoJSONDataSource(geojson=filtered_world.to_json())

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
    (f"Exports ({default_value_type})", "@exports"),
    ("Note", "@note")
]

select_country = Select(title="Select Country", value="", options=sorted(list(admin_to_df_map.keys())), width=220)
select_type = Select(title="Export Type", value=default_type, options=export_types, width=220)
select_value_type = Select(title="Value Type", value=default_value_type, options=value_types, width=220)

# --- Custom styled button ---
top15_button = Button(label="Highlight Top 15", button_type="success", width=220, height=35)
top15_button.css_classes = ["styled-btn"]



reset_button = Button(
    label="🔄",
    button_type="default",
    width=40,
    height=35,
    css_classes=["styled-btn", "reset-btn"]
)

def reset_top15():
    # Restore the map coloring
    exports_log_min = filtered_world["exports_log"].min()
    exports_log_max = filtered_world["exports_log"].max()
    exports_log = filtered_world["exports_log"].values
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)
    filtered_world.loc[filtered_world["ADMIN"] == "China", "custom_color"] = china_color
    geo_source.geojson = filtered_world.to_json()
    # Clear the top 15 table and chart
    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []

reset_button.on_click(reset_top15)

# --- Top 15 Table ---
top15_table_source = ColumnDataSource(data=dict(country=[], value=[]))
top15_table = DataTable(
    source=top15_table_source,
    columns=[
        TableColumn(field="country", title="Country", width=200),
        TableColumn(field="value", title=f"Exports ({default_value_type})", width=150, formatter=formatter)
    ],
    width=370,
    height=350,
    index_position=None,
)

# --- Top 15 Chart (Bar) ---
top15_chart_source = ColumnDataSource(data=dict(country=[], value=[]))
top15_chart = figure(
    x_range=[], height=350, width=370, title=f"Top 15 destinations, {default_type}, {default_value_type}", toolbar_location=None, tools="",
    min_border_left=10, min_border_right=10, min_border_top=10, min_border_bottom=10
)
top15_chart.vbar(x="country", top="value", source=top15_chart_source, width=0.7, color="#556B2F",alpha=0.7)
top15_chart.xaxis.major_label_orientation = 1.0
top15_chart.xgrid.grid_line_color = None
#top15_chart.yaxis.axis_label = f"Exports ({default_value_type})"

# --- DataTable styling ---
selected_table_source = ColumnDataSource(data=dict(index=[], date=[], exports=[]))

date_col = None
for col in df.columns:
    if re.search('date', col, re.IGNORECASE):
        date_col = col
        break

date_width=250
cat_width = 350
total_width = date_width + cat_width

def make_data_table_columns(export_type, value_type):
    return [
        TableColumn(field="date", title="Date", width = date_width),
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
            dates = last_24[date_col].tolist()
        else:
            dates = last_24.index.tolist()
        exports = last_24[df_col].apply(lambda x: round(x,1) if pd.notnull(x) else None).tolist()
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

#selected_table_source.on_change('data', update_div)

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
    filtered_world.loc[filtered_world["ADMIN"] == "China", "custom_color"] = china_color
    geo_source.geojson = filtered_world.to_json()
    p.title.text = f"Automobile Exports by Country ({exp_type}, {value_type})"
    data_table.columns = make_data_table_columns(exp_type, value_type)
    color_mapper_obj.low = exports_log_min
    color_mapper_obj.high = exports_log_max
    color_bar.title = f"Exports ({exp_type}, {value_type})"
    top15_table_source.data = dict(country=[], value=[])
    top15_chart_source.data = dict(country=[], value=[])
    top15_chart.x_range.factors = []

select_type.on_change('value', update_map_type)
select_value_type.on_change('value', update_map_type)

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
        filtered_world["exports_log"] = filtered_world["exports"].apply(
            lambda x: np.log1p(x) if pd.notnull(x) and x > 0 else None
        )
    else:
        filtered_world["exports_log"] = filtered_world["exports"]
    exports_log = filtered_world["exports_log"].values
    valid_indices = np.where(~np.isnan(exports_log))[0]
    top15_idx = valid_indices[np.argsort(exports_log[valid_indices])[::-1][:15]]
    top_admins = set(filtered_world.iloc[top15_idx]["ADMIN"])
    exports_log_min = filtered_world["exports_log"].min()
    exports_log_max = filtered_world["exports_log"].max()
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max, highlight_admins=top_admins)
    filtered_world.loc[filtered_world["ADMIN"] == "China", "custom_color"] = china_color
    geo_source.geojson = filtered_world.to_json()

    # Update top 15 table and chart
    top15_data = filtered_world.iloc[top15_idx][["ADMIN", "exports"]]
    top15_data_sorted = top15_data.sort_values("exports", ascending=False)
    top15_table_source.data = dict(
        country=top15_data_sorted["ADMIN"].tolist(),
        value=top15_data_sorted["exports"].tolist(),
    )
    top15_chart_source.data = dict(
        country=top15_data_sorted["ADMIN"].tolist(),
        value=top15_data_sorted["exports"].tolist(),
    )
    top15_chart.x_range.factors = top15_data_sorted["ADMIN"].tolist()

top15_button.on_click(highlight_top15)

# --- Custom CSS for button ---
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

# --- Controls layout ---
selectors_row = row(
    column(select_country, width=220, sizing_mode="fixed"),
    column(select_type, width=220, sizing_mode="fixed"),
    column(select_value_type, width=220, sizing_mode="fixed"),
    sizing_mode="fixed"
)

# --- Top 15 column (button, chart, table stacked vertically) ---
top15_buttons_row = row(
    top15_button,
    reset_button,
    sizing_mode="fixed"
)

top15_col = column(
    top15_buttons_row,
    top15_chart,
    top15_table,
    sizing_mode="fixed",
    width=370
)

# --- Main row: map on left, highlight chart/table/button on right ---
main_row = row(
    p,
    top15_col,
    sizing_mode="stretch_width",
    height=520   # set height equal to map height for tight layout
)

layout = column(
    style_div,
    main_row,         # map and top 15 to right
    selectors_row,    # selectors directly below map
    selected_div,
    data_table,
    sizing_mode="stretch_width"
)

curdoc().add_root(layout)
curdoc().title = "China, Auto Exports"