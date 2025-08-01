import geopandas as gpd
import pandas as pd
import numpy as np
import difflib
import os
import matplotlib.colors as mcolors
import re

from bokeh.io import curdoc
from bokeh.models import (
    GeoJSONDataSource, Select, Button, ColumnDataSource, HoverTool, Div, Label, NumeralTickFormatter, DatetimeTickFormatter,
    DataTable, TableColumn, HTMLTemplateFormatter, ColorBar, LinearColorMapper, CustomJS
)
from bokeh.plotting import figure
from bokeh.layouts import column, row
from bokeh.themes import Theme

# --- Load large, read-only data globally for efficiency ---
world = gpd.read_file('app/data/ne_10m_admin_0_countries.shp')
df = pd.read_csv('app/data/auto_total.csv')

# --- Find the date column right after loading df ---
date_col = next((col for col in df.columns if re.search('date', col, re.IGNORECASE)), None)
if date_col is not None:
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

# --- Map country names to DataFrame columns ---
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
        country_type_value_to_col.setdefault(country, {}).setdefault(exp_type, {})['USD m'] = col
    elif m2:
        exp_type = m2.group(1)
        country = m2.group(2)
        export_types.add(exp_type)
        value_types.add('% of total')
        country_type_value_to_col.setdefault(country, {}).setdefault(exp_type, {})['% of total'] = col

country_list = list(country_type_value_to_col.keys())
export_types = sorted(list(export_types))
value_types = sorted(list(value_types))

def make_document(doc):
    # --- Theme settings, palettes etc. ---
    theme_json = {
        # ... your theme here ...
    }
    doc.theme = Theme(json=theme_json)
    blues = [
        "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"
    ]
    greens = [
        "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"
    ]
    palette = blues[::-1] + greens
    def interpolate_palette(pal, n):
        cmap = mcolors.LinearSegmentedColormap.from_list('custom', pal)
        return [mcolors.to_hex(cmap(i/(n-1))) for i in range(n)]
    smooth_palette = interpolate_palette(palette, 50)

    default_type = "Total"
    default_value_type = "USD m"
    world_country = 'World'
    latest_row = df.iloc[-1]

    def has_match(admin_name):
        return bool(difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7))
    filtered_world = world[world['ADMIN'].apply(has_match)].reset_index(drop=True)

    admin_to_df_map = {}
    for admin_name in filtered_world['ADMIN']:
        match = difflib.get_close_matches(admin_name, country_list, n=1, cutoff=0.7)
        admin_to_df_map[admin_name] = match[0] if match else None

    # Ensure China is present
    if not (filtered_world["ADMIN"] == "China").any():
        china_row = world[world["ADMIN"] == "China"]
        filtered_world = pd.concat([filtered_world, china_row], ignore_index=True)

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

    def get_colors(export_values, pal, vmin, vmax, highlight_admins=None):
        export_values = np.array(export_values, dtype=float)
        norm = (export_values - vmin) / (vmax - vmin) if (vmax - vmin) != 0 else np.zeros_like(export_values)
        norm = np.clip(norm, 0, 1)
        idx = (norm * (len(pal)-1)).round().astype(int)
        colors = []
        for admin, v, i in zip(filtered_world["ADMIN"], export_values, idx):
            if np.isnan(v):
                colors.append("#dddddd")
            elif highlight_admins is not None and admin not in highlight_admins:
                colors.append("#dddddd")
            else:
                colors.append(pal[i])
        return colors

    exports_log_min = filtered_world["exports_log"].min()
    exports_log_max = filtered_world["exports_log"].max()
    exports_log = filtered_world["exports_log"].values
    filtered_world["custom_color"] = get_colors(exports_log, smooth_palette, exports_log_min, exports_log_max)
    columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
    filtered_world_small = filtered_world[columns_to_keep]
    geo_source = GeoJSONDataSource(geojson=filtered_world_small.to_json())

    # --- Bokeh widgets and sources (session-specific) ---
    world_chart_source = ColumnDataSource(data=dict(date=[], value=[]))
    select_country = Select(title="Select Country", value="", options=sorted(list(admin_to_df_map.keys())), width=220)
    select_type = Select(title="Export Type", value=default_type, options=export_types, width=220)
    select_value_type = Select(title="Value Type", value=default_value_type, options=value_types, width=220)
    top15_button = Button(label="Highlight Top 15", button_type="success", width=220, height=35)
    reset_button = Button(label="🔄", button_type="default", width=40, height=35)
    top15_table_source = ColumnDataSource(data=dict(country=[], value=[]))
    top15_chart_source = ColumnDataSource(data=dict(country=[], value=[]))
    selected_table_source = ColumnDataSource(data=dict(index=[], date=[], exports=[]))
    formatter = HTMLTemplateFormatter(
        template="""<%= (value != null) ? value.toFixed(1) : "N/A" %>"""
    )

    # --- Plots ---
    TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"
    p = figure(
        title=f"China, Auto exports by country, {default_type}, {default_value_type}",
        tools=TOOLS, x_axis_location=None, y_axis_location=None,
        active_scroll='wheel_zoom',
        width=950, height=520,
    )
    p.grid.grid_line_color = None
    color_mapper_obj = LinearColorMapper(palette=smooth_palette, low=exports_log_min, high=exports_log_max, nan_color="#dddddd")
    color_bar = ColorBar(color_mapper=color_mapper_obj, label_standoff=12, location=(0,0),
                        title=f"Exports {default_type}, {default_value_type}")
    p.add_layout(color_bar, 'right')
    p.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=f"www.eastasiaecon.com/cn/#charts"))
    p.xaxis.axis_label = f'Source: CCA, EEA'
    patches = p.patches('xs', 'ys', source=geo_source, fill_color='custom_color',
                        fill_alpha=0.7, line_color="gray", line_width=0.5)
    hover = p.select_one(HoverTool)
    hover.point_policy = "follow_mouse"
    hover.tooltips = [
        ("Country", "@ADMIN"),
        (f"Exports ({default_value_type})", "@exports{0,0.0}"),
        ("Note", "@note")
    ]

    def get_world_timeseries(export_type, value_type):
        world_col = country_type_value_to_col.get(world_country, {}).get(export_type, {}).get(value_type)
        if world_col and world_col in df.columns:
            dates = df[date_col].tolist() if date_col and date_col in df.columns else df.index.tolist()
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

    world_line_chart = figure(
        height=220, width=600,
        title="Monthly World Auto Exports",
        x_axis_type="auto", tools="pan,xwheel_zoom,box_zoom,reset,save",
        margin=(20, 10, 10, 10)
    )
    world_line_chart.line(x="date", y="value", source=world_chart_source, line_width=2, color="#2171b5")
    world_line_chart.yaxis.formatter = NumeralTickFormatter(format="0,0.0")
    world_line_chart.xaxis.formatter = DatetimeTickFormatter(years="%b-%y", months="%b-%y")
    world_line_chart.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen',
                        text=f"www.eastasiaecon.com/cn/#charts"))
    update_world_chart()

    # --- Callbacks (all closures, operate only on session objects) ---
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
            TableColumn(field="date", title="Date", width=200),
            TableColumn(field="exports", title=f"Exports ({export_type}, {value_type})", formatter=formatter, width=350)
        ]

    data_table = DataTable(source=selected_table_source, columns=make_data_table_columns(default_type, default_value_type),
                            width=550, height=400, index_position=None, header_row=True)

    def update_selected(attr, old, new):
        country = select_country.value
        exp_type = select_type.value
        value_type = select_value_type.value
        df_country = admin_to_df_map.get(country)
        df_col = country_type_value_to_col.get(df_country, {}).get(exp_type, {}).get(value_type)
        if df_col and df_col in df.columns:
            last_24 = df.tail(24)
            dates = last_24[date_col].dt.strftime('%y-%b-%d').tolist() if date_col and date_col in df.columns else last_24[date_col].dt.strftime('%y-%b-%d').tolist()
            exports = last_24[df_col].apply(lambda x: round(x, 1) if pd.notnull(x) else None).tolist()
            selected_table_source.data = dict(index=list(range(len(dates))), date=dates, exports=exports)
        else:
            selected_table_source.data = dict(index=[], date=[], exports=[])

    select_country.on_change('value', update_selected)
    select_type.on_change('value', update_selected)
    select_value_type.on_change('value', update_selected)

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

        update_world_chart()
    select_type.on_change('value', update_map_type)
    select_value_type.on_change('value', update_map_type)

    def highlight_top15():
        exports = filtered_world["exports"].values
        valid_indices = np.where(~np.isnan(exports))[0]
        if len(valid_indices) > 15:
            top15_idx = valid_indices[np.argpartition(-exports[valid_indices], 15)[:15]]
        else:
            top15_idx = valid_indices
        top_admins = set(filtered_world.iloc[top15_idx]["ADMIN"].values)
        exports_log = filtered_world["exports_log"].values
        exports_log_min = exports_log[top15_idx].min() if len(top15_idx) > 0 else 0
        exports_log_max = exports_log[top15_idx].max() if len(top15_idx) > 0 else 1
        norm = (exports_log[top15_idx] - exports_log_min) / (exports_log_max - exports_log_min) if exports_log_max != exports_log_min else np.zeros(len(top15_idx))
        idx = (norm * (len(smooth_palette) - 1)).round().astype(int)
        colors = np.full(filtered_world.shape[0], "#dddddd", dtype=object)
        for i, ci in enumerate(top15_idx):
            colors[ci] = smooth_palette[idx[i]]
        filtered_world["custom_color"] = colors

        columns_to_keep = ['ADMIN', 'exports', 'exports_log', 'note', 'custom_color', 'geometry']
        filtered_world_small = filtered_world[columns_to_keep]
        geo_source.geojson = filtered_world_small.to_json()

        top15_data = filtered_world.iloc[top15_idx][["ADMIN", "exports"]].sort_values("exports", ascending=False)
        top15_table_source.data = dict(country=top15_data["ADMIN"].tolist(), value=top15_data["exports"].tolist())
        top15_chart_source.data = dict(country=top15_data["ADMIN"].tolist(), value=top15_data["exports"].tolist())
        top15_chart.x_range.factors = top15_data["ADMIN"].tolist()
    top15_button.on_click(highlight_top15)

    # Compose layout (fill in with your Divs etc.)
    layout = column(
        row(select_type, select_value_type),
        world_line_chart,
        row(p, column(top15_button, reset_button)),
        data_table,
    )
    doc.add_root(layout)
    doc.title = "China, Auto Exports"

curdoc().clear()
make_document(curdoc())