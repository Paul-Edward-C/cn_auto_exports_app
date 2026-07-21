"""Auto-trade panel — world map (pick a partner) + line chart of up to four user-built series.

Workflow: pick the reporting economy, Flow (Exports/Imports), powertrain and measure
(value / units / unit price), click a partner country on the map (or 'World'), then
'Add to chart'. Up to four series — any mix of economy / flow / partner / powertrain /
measure — plot together; a list lets you remove them. House style as cn_auto_exports.

Heavy data lives in shared_data_auto (MultiIndex on economy/flow/category/iso3) — this
function only builds per-session Bokeh models.
"""
import numpy as np
import pandas as pd
from bokeh.layouts import column, row
from bokeh.models import (ColumnDataSource, Select, Button, HoverTool, Div,
                          LinearColorMapper, ColorBar, DataRange1d, LinearAxis,
                          NumeralTickFormatter, DatetimeTickFormatter, Span,
                          Label, SaveTool, Legend, LegendItem)
from bokeh.plotting import figure

from shared_data import (FONT, BRAND, PANEL_BG, MAX_SERIES, SERIES_COLORS, CHART_W, CHART_H,
                         PALETTE, BACKGROUND_URL, WATERMARK,
                         WORLD_XS, WORLD_YS, WORLD_ISO, WORLD_NAME, N_PATCH,
                         COUNTRY_NAMES_SORTED, ISO_IDX, COUNTRY_ISO,
                         REGION_MEMBER_IDX)
from shared_data_auto import (IDX, CUR, ALL_DATES, ECON_LAST,
                              REGION_ISO, REGION_LABELS, REPORTERS, ECON_CATS,
                              FLOWS, ECON_FLOWS, MEASURE_COL, UNIT_LABEL)


def build_auto_panel():
    # ---------------------------------------------------------------- map
    map_src = ColumnDataSource(dict(
        xs=WORLD_XS, ys=WORLD_YS,
        iso3=WORLD_ISO, name=WORLD_NAME,
        hovname=WORLD_NAME, value=[np.nan] * N_PATCH))

    # Linear (not log) — Trade balance can be negative, so the scale must span negatives.
    # Matches the China panel; low/high are set from the data each refresh.
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
                           tooltips=[('', '@hovname'), ('USD bn', '@value{0.000}')]))
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
    ln.title.text = 'Auto trade'

    line_renderers = []
    for i in range(MAX_SERIES):
        r = ln.line('date', f's{i}', source=line_src, name=f's{i}',
                    color=SERIES_COLORS[i], line_width=3, alpha=0.85)
        r.visible = False
        line_renderers.append(r)
        # Per-line hover: show THIS series' value (@s{i}) and the real data month (@date),
        # not the cursor position. 'vline' snaps to the x index; $name = series label.
        ln.add_tools(HoverTool(renderers=[r], mode='vline',
                               tooltips=[('', '$name'), ('value', f'@s{i}{{0,0.000}}'),
                                         ('date', '@date{%b %Y}')],
                               formatters={'@date': 'datetime'}))
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


    legend = Legend(items=[], location='top_left', orientation='vertical',
                    label_text_font=FONT, label_text_font_size='14px',
                    background_fill_alpha=0.7)
    ln.add_layout(legend)

    bg_line_src = ColumnDataSource(dict(url=[BACKGROUND_URL], x=[0], y=[0], w=[1], h=[1]))
    ln.image_url(url='url', x='x', y='y', w='w', h='h', source=bg_line_src,
                 anchor='bottom_left', global_alpha=0.12, level='underlay')
    ln.add_layout(Label(x=10, y=10, x_units='screen', y_units='screen', text=WATERMARK,
                        text_font=FONT, text_font_style='bold', text_font_size='0.875em',
                        text_color='#556B2F', text_alpha=0.8))

    # ---------------------------------------------------------------- styling pass
    for f in (mp, ln):
        f.title.text_font = FONT
        f.title.text_font_style = 'bold'
        f.title.text_font_size = '25px'
        f.axis.axis_label_text_font = FONT
        f.axis.major_label_text_font = FONT

    # ---------------------------------------------------------------- controls
    econ_sel = Select(title='Reporting economy', value='Japan', options=REPORTERS, width=170)
    flow_sel = Select(title='Flow', value='Exports', options=ECON_FLOWS.get('Japan', FLOWS), width=140)
    cat_sel = Select(title='Powertrain', value='Total', options=ECON_CATS['Japan'], width=170)
    measure_sel = Select(title='Measure', value='Value (USD bn)',
                         options=list(MEASURE_COL), width=160)
    add_btn = Button(label='Add to chart', button_type='primary', width=130, height=31, align='end')
    world_btn = Button(label='World', width=110, height=31, align='end')
    country_sel = Select(title='Country', value='Map',
                         options=['Map'] + COUNTRY_NAMES_SORTED, width=200)
    region_sel = Select(title='Region', value='Map', options=['Map'] + REGION_LABELS, width=180)
    partner_label = Div(text='<b>Partner economy</b>',
                        styles={'font-family': FONT, 'font-size': '13px', 'font-weight': 'bold'})
    country_div = Div(text='<b>Partner:</b> <i>click the map, or pick a box</i>',
                      styles={'font-family': FONT, 'font-size': '12px', 'color': '#555'})
    map_instr = Div(text='<i>Pick the reporting economy/options; choose a partner '
                         '(click the map, or Country / Region / World), then “Add to chart”.</i>',
                    styles={'font-family': FONT, 'font-size': '12px', 'color': '#555'})
    series_sel = Select(title='Series on chart (select to remove)', options=[], width=520)
    remove_btn = Button(label='Remove', width=90, height=31, align='end')
    clear_btn = Button(label='Clear all', width=90, height=31, align='end')

    state = {'iso3': None, 'country': None}
    series = []
    busy = {'v': False}

    def _series_values(s):
        # MultiIndex lookup on (economy, flow, category, iso3) — single iso3 -> a DataFrame
        # with a Date column; sum across any remaining duplicate dates with min_count=1.
        key = (s['economy'], s['flow'], s['category'], s['iso3'])
        try:
            sub = IDX.loc[key]
        except KeyError:
            return [np.nan] * len(ALL_DATES)
        if isinstance(sub, pd.Series):
            v = pd.Series({sub['Date']: sub[s['col']]})
        else:
            v = sub.groupby('Date')[s['col']].sum(min_count=1)
        return [float(v.get(d)) if d in v.index else np.nan for d in ALL_DATES]

    def rebuild_chart():
        data = {'date': ALL_DATES}
        items = []
        for i in range(MAX_SERIES):
            col = f's{i}'
            if i < len(series):
                data[col] = _series_values(series[i])
                line_renderers[i].visible = True
                line_renderers[i].name = series[i]['label']   # $name in the hover tooltip
                items.append(LegendItem(label={'value': series[i]['label']},
                                        renderers=[line_renderers[i]]))
            else:
                data[col] = [np.nan] * len(ALL_DATES)
                line_renderers[i].visible = False
        line_src.data = data
        legend.items = items
        series_sel.options = [s['label'] for s in series]

    def add_series():
        if state['iso3'] is None or len(series) >= MAX_SERIES:
            return
        meas = measure_sel.value
        s = dict(country=state['country'], iso3=state['iso3'], economy=econ_sel.value,
                 flow=flow_sel.value, category=cat_sel.value, measure=meas,
                 col=MEASURE_COL[meas])
        s['label'] = (f"{s['economy']}, {s['flow']}, {s['country']}, "
                      f"{s['category']}, {UNIT_LABEL[meas]}")
        if any(x['label'] == s['label'] for x in series):
            return
        series.append(s)
        rebuild_chart()

    def remove_series():
        if series_sel.value:
            series[:] = [s for s in series if s['label'] != series_sel.value]
            rebuild_chart()

    def clear_series():
        series.clear()
        rebuild_chart()

    def refresh_map():
        # Colour map by selected reporter's Flow + Powertrain (USD bn) at THAT reporter's
        # latest month. MultiIndex lookup on (economy, flow, category) -> rows for all iso3.
        econ, cat, flow = econ_sel.value, cat_sel.value, flow_sel.value
        edate = ECON_LAST.get(econ, CUR)
        try:
            sub = IDX.loc[(econ, flow, cat)]
        except KeyError:
            sub = None
        if sub is None or len(sub) == 0:
            map_src.data['value'] = [np.nan] * len(map_src.data['iso3'])
            mp.title.text = f'{econ}, {flow}, {cat}, USD bn — no data'
            return
        # Index is now iso3; pick the reporter's latest month rows and sum per iso3.
        at_date = sub[sub['Date'] == edate]
        by_iso = at_date.groupby(level=0, observed=True)['value'].sum()
        vals = [by_iso.get(i, np.nan) for i in map_src.data['iso3']]
        vals = [v if (v is not None and v == v) else np.nan for v in vals]
        map_src.data['value'] = vals
        # Linear range from the data (Trade balance can be negative → deficits at the low end).
        finite = [v for v in vals if v == v]
        if finite:
            lo, hi = min(finite), max(finite)
            color_mapper.low, color_mapper.high = (lo, hi) if lo != hi else (lo, lo + 1)
        mp.title.text = f'{econ}, {flow}, {cat}, USD bn, {edate:%b %Y}'

    def on_tap(attr, old, new):
        if busy['v']:
            return
        if new:
            i = new[0]
            iso, name = map_src.data['iso3'][i], map_src.data['name'][i]
            state['iso3'], state['country'] = iso, name
            country_div.text = f'<b>Partner:</b> {name}'
            busy['v'] = True
            country_sel.value = name if name in COUNTRY_ISO else 'Map'
            region_sel.value = 'Map'
            busy['v'] = False
        else:
            state['iso3'] = state['country'] = None
            country_div.text = '<b>Partner:</b> <i>click the map, or pick a box</i>'

    def pick_country(attr, old, new):
        if busy['v'] or new == 'Map':
            return
        iso = COUNTRY_ISO[new]
        state['iso3'], state['country'] = iso, new
        busy['v'] = True
        map_src.selected.indices = [ISO_IDX[iso]] if iso in ISO_IDX else []
        region_sel.value = 'Map'
        busy['v'] = False
        country_div.text = f'<b>Partner:</b> {new}'

    def use_world():
        busy['v'] = True
        map_src.selected.indices = []
        country_sel.value = 'Map'
        region_sel.value = 'Map'
        busy['v'] = False
        state['iso3'], state['country'] = 'WLD', 'World'
        country_div.text = '<b>Partner:</b> World'

    def pick_region(attr, old, new):
        if busy['v'] or new == 'Map':
            return
        busy['v'] = True
        map_src.selected.indices = REGION_MEMBER_IDX.get(new, [])
        country_sel.value = 'Map'
        busy['v'] = False
        state['iso3'], state['country'] = REGION_ISO[new], new
        country_div.text = f'<b>Partner:</b> {new} (region)'

    map_src.selected.on_change('indices', on_tap)
    add_btn.on_click(add_series)
    world_btn.on_click(use_world)
    country_sel.on_change('value', pick_country)
    region_sel.on_change('value', pick_region)
    remove_btn.on_click(remove_series)
    clear_btn.on_click(clear_series)

    def on_econ_change(attr, old, new):
        opts = ECON_CATS.get(new, ['Total'])
        cat_sel.options = opts
        if cat_sel.value not in opts:
            cat_sel.value = 'Total' if 'Total' in opts else opts[0]
        # Trade balance is only available for some reporters (Japan/Korea) — keep the Flow
        # options in sync so it isn't offered where the data can't supply it.
        fopts = ECON_FLOWS.get(new, FLOWS)
        flow_sel.options = fopts
        if flow_sel.value not in fopts:
            flow_sel.value = 'Exports' if 'Exports' in fopts else fopts[0]
        refresh_map()

    econ_sel.on_change('value', on_econ_change)
    flow_sel.on_change('value', lambda a, o, n: refresh_map())
    cat_sel.on_change('value', lambda a, o, n: refresh_map())

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
                      '#104b1f;padding-bottom:6px;margin-bottom:4px;">Auto trade — passenger '
                      'cars by market</h2>', sizing_mode='stretch_width')
    footer = Div(text='<div style="font-family:Georgia;font-size:12px;color:#333;border-top:'
                      f'1px solid #104b1f;padding-top:6px;">Source: EAE, national sources / UN '
                      f'Comtrade. Latest: {CUR:%b %Y}.  <a href="https://www.eastasiaecon.com" '
                      'style="color:#556B2F;font-weight:bold;text-decoration:none;">'
                      'www.eastasiaecon.com</a></div>', sizing_mode='stretch_width')

    refresh_map()
    rebuild_chart()
    return column(header,
                  row(econ_sel),
                  column(partner_label, row(country_sel, region_sel, world_btn)),
                  row(flow_sel, cat_sel, measure_sel, add_btn),
                  row(series_sel, remove_btn, clear_btn),
                  map_instr,
                  row(mp, ln),
                  footer, sizing_mode='stretch_width')
