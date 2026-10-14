"""Stage CIS's 1991-2020 reference climatologies (EC) into the product archive as runs.

Reads the date-of-event shapefiles under
``~/data/CIS/1991-2020_climatology_shapefiles/EC/{freezeup,breakup,fast_ice}`` — one
externally computed product per field, each a set of polygons carrying a weekly
``MMDD`` date — and burns one onto a region's own grid as a `.npz` + `.json` pair under
`output/`. The result is addressable as an ordinary run (`--source cis`), so
`plot/build.py --type delta` can difference it against our products.

CIS builds these from weekly median-concentration charts, then thresholds them (4/10 for
freeze-up/break-up, 1/10 for first/last occurrence) — the median-then-threshold order
our own ``mediantt`` reducer computes, which is the coordinate each layer is filed under.

The polygons are the *result*, not chart observations: the `FetchResult` they travel in
carries no season calendar, and its `n_polygons` counts the source polygons. A value
burns by cell centre (``burn_values``) and is then masked to the tier's wet domain, so
the footprint matches our products'. That mask is what defines land here: CIS's own
off-calendar values (``'0'``, ``'L'``, null) are all read as no-data, because ``'0'``
also covers land in the files without an ``'L'`` class and so cannot be read as
"never any ice".

This is a staging step, not a probe: it writes a product. It does not touch the DB.

Run:
    python climatology/scripts/import_cis_climatology.py [--field first]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.core.context import FetchResult, Result, RunContext
from climatology.core.export import archive_product
from climatology.core.rasterize import burn_mask, burn_values
from climatology.core.regions import Tier
from climatology.services.calendar import day_of_season
from climatology.utils._types import DataGrid

log = logging.getLogger(__name__)

CIS_ROOT = Path.home() / "data" / "CIS" / "1991-2020_climatology_shapefiles" / "EC"
GRID_CRS = "EPSG:32198"          # NAD83 / MTM 8 — what the region tiers grid in
REGION = "golfe"                 # the EC charts' extent; the grid every layer burns onto
PERIOD = "1991-2020"
REDUCTION = "mediantt"           # CIS thresholds weekly median charts

# Which subfolder each field's shapefile sits in, and which run coordinate it is the
# product of. The shapefile and its value column share the field's name.
FIELD_METRICS: dict[str, tuple[str, str]] = {
    "first":  ("freezeup", "first_occurrence"),
    "freeze": ("freezeup", "freeze_up"),
    "break":  ("breakup",  "breakup"),
    "last":   ("breakup",  "last_occurrence"),
    "fifup":  ("fast_ice", "landfast_freeze_up"),
}

# Every value off the weekly calendar observed across the five files: '0' (no event, and
# land where a file has no 'L' class), 'L' (land, break only), null (land, fifup only).
NO_EVENT = frozenset({"0", "L"})


def load_layer(field: str) -> gpd.GeoDataFrame:
    """One field's polygons, repaired and reprojected onto the grid CRS."""
    subdir, _ = FIELD_METRICS[field]
    gdf = gpd.read_file(CIS_ROOT / subdir / f"{field}.shp")[[field, "geometry"]]
    gdf["geometry"] = gdf.geometry.make_valid()
    log.info("Read %s.shp: %s polygons, %d distinct values",
             field, f"{len(gdf):,}", gdf[field].nunique(dropna=False))
    return gdf.to_crs(GRID_CRS)


def _season_day(mmdd: str | None) -> float:
    """Sep-1-anchored ordinal of an ``MMDD`` value; NaN for CIS's no-event and land codes."""
    if mmdd is None or mmdd != mmdd or mmdd in NO_EVENT:   # mmdd != mmdd: pandas NaN
        return np.nan
    if len(mmdd) != 4 or not mmdd.isdigit():
        raise KeyError(f"Unmapped CIS climatology value {mmdd!r}")
    return float(day_of_season(f"{mmdd[:2]}-{mmdd[2:]}"))


def rasterize(gdf: gpd.GeoDataFrame, field: str, tier: Tier) -> DataGrid:
    """The field's season ordinals burned on ``tier``'s grid, NaN off its wet domain."""
    days = gdf[field].map(_season_day).to_numpy(dtype="float32")
    values = burn_values(gdf.geometry, days, tier.grid)[0]
    values[~burn_mask([tier.wet], tier.grid)] = np.nan
    defined = values[np.isfinite(values)]
    log.info("Burned %s on %d x %d cells: %s defined, days %.0f..%.0f",
             field, tier.grid.height, tier.grid.width, f"{defined.size:,}",
             defined.min(), defined.max())
    return values


def run(field: str) -> Path:
    """Stage one CIS field as an archived product of ``REGION``; returns the .npz path."""
    _, metric = FIELD_METRICS[field]
    ctx = RunContext.build(REGION, metric, PERIOD, "cis", REDUCTION)
    tier, = ctx.region.tiers   # 'full' only — a branching region has no single target grid

    gdf = load_layer(field)
    # Bypasses ``FetchResult.build``: these are result polygons with no T1 to calendar.
    return archive_product(ctx, FetchResult(df=gdf),
                           Result(tier=tier, values=rasterize(gdf, field, tier)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--field", nargs="+", default=list(FIELD_METRICS),
                   choices=list(FIELD_METRICS), help="Which CIS fields to stage (default: all).")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    if not CIS_ROOT.exists():
        sys.exit(f"not found: {CIS_ROOT}")
    for field in args.field:
        print(run(field))


if __name__ == "__main__":
    main()
