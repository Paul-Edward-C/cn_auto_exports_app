"""EAE trade dashboards — entry point.

Two tabs: China trade (cn_auto_exports) and Auto trade (region_auto_bokeh).
Bokeh re-runs this script per session, so we keep it thin: each panel's heavy data sits
in shared_data_cn / shared_data_auto (loaded once per process). The two builders return
their layouts and we wrap them in a Tabs widget.

    bokeh serve --show app
"""
from bokeh.io import curdoc
from bokeh.layouts import column
from bokeh.models import TabPanel, Tabs, InlineStyleSheet, Div

from shared_data import BRAND, SAGE, CREAM, FONT
from panel_cn import build_cn_panel
from panel_auto import build_auto_panel

# Forest-green brand banner (East Asia Econ 2025 identity: forest green + cream, serif).
header = Div(sizing_mode='stretch_width', styles={'margin': '0 0 10px 0'}, text=f"""
<div style="background:{BRAND}; padding:14px 26px; border-radius:5px;
            display:flex; align-items:baseline; gap:16px;">
  <span style="font-family:{FONT},serif; font-size:27px; font-weight:bold; color:{CREAM};
               letter-spacing:0.5px;">East&nbsp;Asia&nbsp;Econ</span>
  <span style="font-family:{FONT},serif; font-size:14px; color:{SAGE}; letter-spacing:3px;
               text-transform:uppercase;">Trade&nbsp;Dashboards</span>
</div>
""")

# Tabs styled to the brand: active tab is a forest-green fill with cream text (like the
# newsletter header); inactive tabs sit muted on cream; forest-green rule underneath.
tabs_style = InlineStyleSheet(css=f"""
:host {{ border-bottom: 3px solid {BRAND}; margin-bottom: 8px; }}
.bk-tab {{
  font-family: {FONT}, serif;
  font-size: 22px;
  font-weight: bold;
  padding: 11px 34px;
  color: {SAGE};
  background: #faf7f0;
  border: 1px solid #ded7c7;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  margin-right: 6px;
}}
.bk-tab:hover {{ color: {BRAND}; background: #eef2e6; }}
.bk-tab.bk-active {{
  color: {CREAM};
  background: {BRAND};
  border-color: {BRAND};
  border-bottom: 3px solid {BRAND};
}}
""")

tabs = Tabs(tabs=[
    TabPanel(child=build_cn_panel(), title='China trade'),
    TabPanel(child=build_auto_panel(), title='Auto trade'),
], sizing_mode='stretch_width', stylesheets=[tabs_style])

curdoc().add_root(column(header, tabs, sizing_mode='stretch_width'))
curdoc().title = 'EAE trade dashboards'
