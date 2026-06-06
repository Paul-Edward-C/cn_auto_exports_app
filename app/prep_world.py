"""Precompute a lightweight, simplified world-geometry file for the Bokeh map.

The app normally loads the full 25 MB ne_10m GeoJSON (~550k vertices) and ships
every coordinate to the browser, which makes panning/zooming the map sluggish.
This script simplifies each country's polygons once (big vertex reduction) and
writes a compact parquet that `app/main.py:load_world_geometry()` loads instead.

The parquet preserves the original feature *properties* (so ADMIN matching,
ADMIN_DISPLAY, etc. are unchanged) and stores the simplified geometry as a
GeoJSON dict — identical in shape to what the GeoJSON path produced, just lighter.
Run offline whenever the source geometry changes:

    /Users/paul/opt/anaconda3/bin/python app/prep_world.py
"""
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import shape, mapping

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "ne_10m_admin_0_countries.geojson"
OUT = HERE / "data" / "world_patches_simplified.parquet"
TOL = 0.15            # simplify tolerance in degrees (~16 km) -> light geometry


def _count_vertices(geom_dict):
    t, coords = geom_dict.get("type"), geom_dict.get("coordinates", [])
    if t == "Polygon":
        return sum(len(ring) for ring in coords)
    if t == "MultiPolygon":
        return sum(len(ring) for poly in coords for ring in poly)
    return 0


def main():
    gj = json.load(open(SRC, encoding="utf-8"))
    rows = []
    v_before = v_after = 0
    for feat in gj["features"]:
        props = feat["properties"]
        orig = feat["geometry"]
        v_before += _count_vertices(orig)

        # Simplify; buffer(0) first to repair any self-intersections.
        geom = shape(orig).buffer(0).simplify(TOL, preserve_topology=True)
        simplified = mapping(geom) if not geom.is_empty else None

        # Fall back to the original geometry rather than drop a country if the
        # simplified result is empty or not a (Multi)Polygon.
        if simplified is None or simplified.get("type") not in ("Polygon", "MultiPolygon"):
            simplified = orig
        v_after += _count_vertices(simplified)

        rows.append({
            "ADMIN": props.get("ADMIN"),
            "props_json": json.dumps(props),
            "geometry_json": json.dumps(simplified),
        })

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(
        f"saved {OUT.name}  {len(df)} countries, "
        f"{v_after:,} vertices (down from {v_before:,}, "
        f"{100 * (1 - v_after / v_before):.1f}% reduction); "
        f"{OUT.stat().st_size / 1e6:.2f} MB on disk vs {SRC.stat().st_size / 1e6:.1f} MB source"
    )


if __name__ == "__main__":
    main()
