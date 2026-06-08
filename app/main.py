"""EAE trade dashboards — entry point.

Two tabs: China trade (cn_auto_exports) and Auto trade (region_auto_bokeh).
Bokeh re-runs this script per session, so we keep it thin: each panel's heavy data sits
in shared_data_cn / shared_data_auto (loaded once per process). The two builders return
their layouts and we wrap them in a Tabs widget.

    bokeh serve --show app
"""
from bokeh.io import curdoc
from bokeh.models import TabPanel, Tabs

from panel_cn import build_cn_panel
from panel_auto import build_auto_panel

tabs = Tabs(tabs=[
    TabPanel(child=build_cn_panel(), title='China trade'),
    TabPanel(child=build_auto_panel(), title='Auto trade'),
], sizing_mode='stretch_width')

curdoc().add_root(tabs)
curdoc().title = 'EAE trade dashboards'
