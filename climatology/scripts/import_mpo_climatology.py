"""Stage DFO's IceGridOccurrence climatology into the product archive as a run.

Reads `~/data/MPO/IceGridOccurrence.GEC.climatology.dat` — an externally computed
reference product (GEC, 1991-2020, one row per cell, longitude stored positive-west;
column format per P. Galbraith 2026-07-09) — and writes one of its fields onto a
region's own grid as a `.npz` + `.json` pair under `output/`. The result is
addressable as an ordinary run (`--source mpo`), so `plot/build.py --type delta`
can difference it against our products without knowing where it came from.

Two alignments, on different axes. *Calendar*: the `.dat` dates a day by its signed
distance from Dec 31, our metrics from Sep 1, so the date fields are re-anchored by a
constant (`_align_values`); a duration is a length, not an instant, and passes through.
*Geometry*: the `.dat` lattice is regular (0.015 deg lon x 0.01 deg lat, measured
uniform to 1e-6; probe 027), so rasterizing it on its own lattice is lossless — every
row lands in exactly one cell by integer index — and that raster is reprojected onto the
region tier's grid with **nearest neighbour**. Every field here is a day-of-season
ordinal or a count of observation-weeks, so interpolation would invent non-representable
values (DEC-035).

A cell is no-data here for either of two reasons. It is *absent from the file* — cells
with zero ice occurrence are not listed — and stays NaN rather than being filled as
zero, because the file does not distinguish "never any ice" from "outside the GEC
domain" and inventing the difference would bias any comparison. Or it fails MPO's own
coverage gate (`_keep_valid`), which the `.dat` does not have applied. Consumers read a
NaN as no-data, so the MPO-minus-ours delta is defined only where MPO both lists a cell
and stands behind it.

This is a staging step, not a probe: it writes a product. It does not touch the DB.

Run:
    python climatology/scripts/import_mpo_climatology.py [--field duration_d]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.core.context import FetchResult, Result, RunContext
from climatology.core.export import archive_product
from climatology.utils._types import Grid

log = logging.getLogger(__name__)

DAT = Path.home() / "data" / "MPO" / "IceGridOccurrence.GEC.climatology.dat"
DAT_CRS = "EPSG:4326"
GRID_CRS = "EPSG:32198"          # NAD83 / MTM 8 — what the region tiers grid in
LON_RES, LAT_RES = 0.015, 0.01   # the .dat's lattice step (probe 027)
COLUMNS = ("lon_w", "lat", "first_doy", "first_dt", "last_doy", "last_dt",
           "duration_d", "n_years")

# The .dat dates a day by its signed distance from Dec 31 (negative into the previous
# December); our metrics are Sep-1-anchored (``services.calendar.day_of_season``).
# Verified against the file's own MM-DD rendering: signed 35 -> 02-04, 172 -> 06-21,
# -29 -> 12-02, all exactly day_of_season - 121.
DOY_OFFSET = 121
DOY_FIELDS = frozenset({"first_doy", "last_doy"})

# MPO's downstream pixel rule — "un minimum de 15 annees de presence de glace sur les 30"
# (Galbraith, pers. comm. 2026-08-17). The `.dat` is the *pre-gate* intermediate: 38% of
# its rows sit below the bar, so the gate is ours to apply here. Probe 027 gates the same
# way, on the same side of the boundary (>= keeps the 1.26% of cells at exactly 15).
MPO_MIN_COVERAGE = 15

# Which run coordinate each field is the product of. The .dat is a threshold-then-
# fixed-denominator-mean over CT >= 1/10 (probe 027, DEC-053) — `ttmpo` is the slug
# our own reducer carries for that same order, which is what makes the delta legible.
FIELD_METRICS: dict[str, tuple[str, str]] = {
    "duration_d": ("season_duration_10", "ttmpo"),
    "first_doy": ("first_occurrence_date", "ttmpo"),
    "last_doy": ("last_occurrence_date", "ttmpo"),
}
PERIOD = "1991-2020"


def load_dat(path: Path) -> pd.DataFrame:
    """`.dat` -> DataFrame with signed longitude (the file stores positive-west)."""
    df = pd.read_csv(path, sep=r"\s+", header=None, names=list(COLUMNS),
                     dtype={"first_dt": str, "last_dt": str})
    df["lon"] = -df["lon_w"]
    log.info("Read %s: %s rows, lon %.3f..%.3f, lat %.3f..%.3f",
             path.name, f"{len(df):,}", df.lon.min(), df.lon.max(),
             df.lat.min(), df.lat.max())
    return df


def _keep_valid(df: pd.DataFrame, field: str) -> pd.Series:
    """``field`` with the under-covered cells dropped to NaN (MPO's minimum of 15 ice seasons in 30).

    Gates the *values*, not the rows, so the gate can never move the lattice: a dropped
    cell becomes no-data in place rather than an absent row that would pull the bbox in.
    """
    under = df["n_years"] < MPO_MIN_COVERAGE
    log.info("Coverage gate n_years >= %d: dropped %s of %s cells (%.1f%%)",
             MPO_MIN_COVERAGE, f"{int(under.sum()):,}", f"{len(df):,}",
             100.0 * under.mean())
    return df[field].mask(under)


def rasterize_native(df: pd.DataFrame, field: str) -> tuple[np.ndarray, object]:
    """One field on the .dat's own lattice, NaN where the file lists no cell or the gate drops it.

    Lossless: the lattice is regular, so the integer index of a row *is* its cell.
    Bounds are pushed out half a cell because the stored coordinates are centres.
    """
    col = np.rint((df.lon - df.lon.min()) / LON_RES).astype(int)
    row = np.rint((df.lat.max() - df.lat) / LAT_RES).astype(int)   # north-up
    values = np.full((row.max() + 1, col.max() + 1), np.nan, dtype="float32")
    values[row, col] = _keep_valid(df, field).to_numpy(dtype="float32")

    transform = from_bounds(df.lon.min() - LON_RES / 2, df.lat.min() - LAT_RES / 2,
                            df.lon.max() + LON_RES / 2, df.lat.max() + LAT_RES / 2,
                            values.shape[1], values.shape[0])
    filled = int(np.isfinite(values).sum())
    log.info("Native lattice: %d x %d cells, %s listed (%.1f%% of the bbox)",
             values.shape[0], values.shape[1], f"{filled:,}",
             100.0 * filled / values.size)
    return values, transform


def _align_values(values: np.ndarray, field: str) -> np.ndarray:
    """A date field re-anchored to the season origin; any other field unchanged.

    A calendar alignment, not the geometric one ``align_to`` does. The shift is a
    constant, so it commutes with the resampling and NaN stays NaN. ``duration_d`` is a
    length rather than an instant and passes through.

    No row is masked: the ``00-00`` rendering in ``last_dt`` reads like a no-data flag
    but is not one — those 54 rows carry a finite 0.9 in both date columns, the fixed-30
    denominator acting on a cell with a single ice season.
    """
    if field not in DOY_FIELDS:
        return values
    shifted = values + DOY_OFFSET
    finite = shifted[np.isfinite(shifted)]
    log.info("Re-anchored %s to the season origin: %.1f..%.1f (was %.1f..%.1f)",
             field, finite.min(), finite.max(),
             finite.min() - DOY_OFFSET, finite.max() - DOY_OFFSET)
    return shifted


def align_to(values: np.ndarray, transform, grid: Grid, crs: str) -> np.ndarray:
    """The native raster resampled onto ``grid`` (nearest; NaN outside the .dat footprint)."""
    dst = np.full((grid.height, grid.width), np.nan, dtype="float32")
    reproject(
        source=values, destination=dst,
        src_transform=transform, src_crs=DAT_CRS,
        dst_transform=grid.transform, dst_crs=crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan, dst_nodata=np.nan,
    )
    defined = int(np.isfinite(dst).sum())
    log.info("Aligned to %s: %d x %d cells, %s defined (%.1f%%)",
             crs, grid.height, grid.width, f"{defined:,}",
             100.0 * defined / dst.size)
    return dst


def run(field: str, region: str, period: str) -> Path:
    """Stage one .dat field as an archived product of ``region``; returns the .npz path."""
    metric, reduction = FIELD_METRICS[field]
    ctx = RunContext.build(region, metric, period, "mpo", reduction)
    tier, = ctx.region.tiers   # 'full' only — a branching region has no single target grid

    native, transform = rasterize_native(load_dat(DAT), field)
    aligned = align_to(_align_values(native, field), transform, tier.grid, GRID_CRS)

    # Through the ordinary archive writer, so naming, manifest and git provenance stay
    # in sync with a real run. n_polygons is 0: nothing was fetched.
    return archive_product(ctx, FetchResult(df=pd.DataFrame()),
                           Result(tier=tier, values=aligned))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--field", default="duration_d", choices=sorted(FIELD_METRICS),
                   help="Which .dat column to stage.")
    p.add_argument("--region", default="golfe", help="Region whose grid to align onto.")
    p.add_argument("--period", default=PERIOD, help="Period the .dat covers.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    if not DAT.exists():
        sys.exit(f"not found: {DAT}")
    print(run(args.field, args.region, args.period))


if __name__ == "__main__":
    main()
