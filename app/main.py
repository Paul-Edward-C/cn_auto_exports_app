"""EAE trade dashboards — entry point.

Two tabs: China trade (cn_auto_exports) and Auto trade (region_auto_bokeh).
Bokeh re-runs this script per session, so we keep it thin: each panel's heavy data sits
in shared_data_cn / shared_data_auto (loaded once per process). The two builders return
their layouts and we wrap them in a Tabs widget.

    bokeh serve --show app
"""
from bokeh.io import curdoc
from bokeh.models import TabPanel, Tabs, InlineStyleSheet

from panel_cn import build_cn_panel
from panel_auto import build_auto_panel

# Make the two tabs large and obvious — big Georgia labels, generous padding, and a clear
# highlight on the active tab so it reads as a real two-way switch, not small text.
tabs_style = InlineStyleSheet(css="""
:host { border-bottom: 2px solid #104b1f; margin-bottom: 6px; }
.bk-tab {
  font-family: Georgia, serif;
  font-size: 22px;
  font-weight: bold;
  padding: 12px 34px;
  color: #6b6b6b;
  border: 1px solid #d6e0d6;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  margin-right: 6px;
}
.bk-tab:hover { color: #104b1f; background: #eef5ee; }
.bk-tab.bk-active {
  color: #104b1f;
  background: #f4f9f4;
  border-color: #104b1f;
  border-bottom: 3px solid #f4f9f4;
}
""")

tabs = Tabs(tabs=[
    TabPanel(child=build_cn_panel(), title='China trade'),
    TabPanel(child=build_auto_panel(), title='Auto trade'),
], sizing_mode='stretch_width', stylesheets=[tabs_style])

curdoc().add_root(tabs)
curdoc().title = 'EAE trade dashboards'
