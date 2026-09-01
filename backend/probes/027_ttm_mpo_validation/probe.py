"""Probe 027 — identify the Reduction behind MPO's IceGridOccurrence.GEC climatology.

Goal: find the reduction that reproduces `~/data/MPO/IceGridOccurrence.GEC.climatology.dat`
(GEC, 1991-2020, weekly SGRDREC charts; column format per P. Galbraith 2026-07-09).
This probe identifies *their* method; it does not compare it to MTT/TTM.

Settled so far:
  order       threshold first, then the cross-season statistic.
  statistic   sum of the per-season values over the seasons that HAVE ice,
              divided by a FIXED 30 — ice-free seasons enter the sum as 0
              (signed Jan-1 DOY 0 = Dec 31), they are not excluded.
  gate        "un minimum de 15 annees de presence de glace sur les 30"
              (Galbraith, pers. comm. 2026-08-17) is applied *downstream* of
              this file: 38 % of its rows sit below that bar, 8.3 % at N=1.
              So the `.dat` is the pre-gate intermediate.

Computed on the `.dat`'s OWN lattice — a regular geographic grid, 0.015 deg lon
x 0.01 deg lat, EPSG:4326, longitude stored positive-west — rather than
resampling either side onto the project's 32198 metric grid. The two have nearly
equal cell size (~1.1 km), which is the worst case for nearest-neighbour
sampling, so co-locating them this way removes the registration term from the
residual entirely. Only the Tier's `grid` and `wet_mask` are swapped; the
polygon burn and the kernel fold are CRS- and grid-agnostic, and the wet mask is
the `.dat`'s own footprint (it lists only cells with >= 1 ice occurrence).

Because the lattice is geographic, polygons are read from the 4326 `sgrdr` table
rather than the pre-projected `sgrdr_32198` view the production SQL targets.

No write-back; reads the `.dat` and the `sgrdr` table read-only.
Output: timestamped txt scorecard + one delta PNG per quantity under output/.

Run:
    .venv/bin/python -m backend.probes.027_ttm_mpo_validation.probe
"""

from __future__ import annotations

import argparse
import operator
import re
import textwrap
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import shapely

matplotlib.use("Agg")
import matplotlib.colors as colors
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from rasterio.transform import from_bounds, rowcol

load_dotenv(Path(__file__).parents[3] / ".env")

from climatology.processing.conversion import CONCENTRATION_FRACTION
from climatology.processing.metrics import METRICS
from climatology.utils._types import Grid
from climatology.processing.reductions import (
    ThresholdDate,
    ThresholdDuration,
    _stream_day_stacks,
)
from climatology.processing.regions import Tier
from climatology.services.db import load_polygons
from climatology.services.temporal import Period, attach_season_calendar

DAT = Path("/home/eliedl/data/MPO/IceGridOccurrence.GEC.climatology.dat")
OUT = Path(__file__).parent / "output"

PERIOD = "1991-2020"
N_SEASONS = 30       # the FIXED denominator — not a count of contributing seasons
CT_THRESHOLD = 0.1   # occurrence threshold (MPO README: CT >= 1/10)
DOY_OFFSET = 121     # day_of_season (Sep-1 anchored) - 121 = signed Jan-1 DOY
WEEK_DAYS = 7.0      # weekly HD cadence -> observation-weeks to days
MPO_GATE = 15        # the downstream ">= 15 of 30" pixel rule, tested but NOT applied here
LON_RES, LAT_RES = 0.015, 0.01   # the .dat's lattice step, measured (uniform to 1e-6)


# --- Phase A: the file, on its own terms (no DB) ------------------------------

def load_mpo() -> pd.DataFrame:
    """`.dat` -> DataFrame with signed longitude; no reprojection (we adopt its lattice)."""
    cols = ["lon_w", "lat", "first_doy", "first_dt", "last_doy", "last_dt",
            "duration_d", "n_years"]
    df = pd.read_csv(DAT, sep=r"\s+", header=None, names=cols,
                     dtype={"first_dt": str, "last_dt": str})
    df["lon"] = -df["lon_w"]
    return df


def decode_checks(mpo: pd.DataFrame) -> list[str]:
    """Internal-consistency census of the .dat (no DB)."""
    n = mpo.n_years
    sent = mpo.last_dt.eq("00-00")
    return [
        "Phase A — the .dat on its own terms",
        f"  rows {len(mpo):,} | N range {n.min()}-{n.max()} | N==30: {(n == 30).mean() * 100:.1f}%",
        f"  first_doy range {mpo.first_doy.min():.1f} .. {mpo.first_doy.max():.1f}"
        f" | last_doy range {mpo.last_doy.min():.1f} .. {mpo.last_doy.max():.1f}"
        f" | duration range {mpo.duration_d.min():.1f} .. {mpo.duration_d.max():.1f}",
        f"  '00-00' sentinel rows: {sent.sum():,}"
        + (f" | their N: {sorted(n[sent].unique())[:8]}" if sent.any() else ""),
        f"  rows below the downstream gate (N < {MPO_GATE}): {(n < MPO_GATE).sum():,}"
        f" ({(n < MPO_GATE).mean() * 100:.1f}%) | N == 1: {(n == 1).sum():,}",
        "",
    ]


# --- Phase B: adopt the .dat's lattice as the tier grid ------------------------

def dat_tier(mpo: pd.DataFrame) -> tuple[Tier, np.ndarray]:
    """A 'full' Tier whose grid IS the .dat lattice; returns it with the row index of each cell.

    The `.dat` stores one point per cell, so the lattice is reconstructed from the
    coordinate steps and the bounds are pushed out half a cell (points read as cell
    centres). `grid` and `wet_mask` are written straight into the instance dict —
    they are `cached_property`, so a pre-seeded entry is what every consumer sees,
    and the region polygon behind them is never consulted.
    """
    xmin, xmax = mpo.lon.min() - LON_RES / 2, mpo.lon.max() + LON_RES / 2
    ymin, ymax = mpo.lat.min() - LAT_RES / 2, mpo.lat.max() + LAT_RES / 2
    width = int(round((xmax - xmin) / LON_RES))
    height = int(round((ymax - ymin) / LAT_RES))
    grid = Grid(from_bounds(xmin, ymin, xmax, ymax, width, height),
                height, width, (xmin, ymin, xmax, ymax))

    r, c = rowcol(grid.transform, mpo.lon.to_numpy(), mpo.lat.to_numpy())
    r, c = np.asarray(r), np.asarray(c)
    if not ((r >= 0).all() and (r < height).all() and (c >= 0).all() and (c < width).all()):
        raise ValueError("a .dat row falls outside the lattice reconstructed from its own steps")
    wet_mask = np.zeros((height, width), dtype=bool)
    wet_mask[r, c] = True

    tier = Tier("full", LAT_RES, shapely.geometry.box(xmin, ymin, xmax, ymax))
    tier.__dict__["grid"] = grid
    tier.__dict__["wet_mask"] = wet_mask
    # .dat row -> position in the wet-cell vectors the kernels return
    order = np.full((height, width), -1, dtype=np.int64)
    order[wet_mask] = np.arange(int(wet_mask.sum()))
    return tier, order[r, c]


def fetch_prepared(tier: Tier, *, source: str = "sgrdr"):
    """Polygons for the lattice, in 4326, from either source — one ConvertedPolygons contract.

    ``gec_h`` swaps the loader for MPO's own archive and skips the HD-alignment
    assertion: GEC_H is deliberately off the Historical-Date calendar (282 distinct
    MM-DD against sgrdr's rigid 52), so that guard would correctly reject it.
    """
    if source == "gec_h":
        df = load_gec_h_polygons()
        return METRICS["first_occurrence_date"].conversion.prepare(attach_season_calendar(df))
    start, end = Period(PERIOD).window
    bbox = tier.fetch_wkt
    sql = f"""
        SELECT ST_AsBinary(ST_Intersection(geometry, ST_GeomFromText('{bbox}', 4326))) AS geom_wkb,
               "T1"::date AS obs_date,
               "CT" AS ct_code
        FROM sgrdr
        WHERE ST_Intersects(geometry, ST_GeomFromText('{bbox}', 4326))
          AND "T1" >= '{start}' AND "T1" < '{end}'
        ORDER BY obs_date;
    """
    df = load_polygons(sql)
    return METRICS["first_occurrence_date"].conversion.prepare(attach_season_calendar(df))


# --- Phase B': MPO's own source — the GEC_H shapefiles, read straight from disk ---
#
# GEC_H is the archive MPO actually rasterizes (confirmed by the operator). It is NOT
# the normalized `sgrdr` table: it is the raw SGRDREC feed, in three schemas (measured
# across all 1,028 in-window charts; one further chart, 20190822, carries only FID).
#
#   era 1  995 charts, from 1990-12-20  A_LEGEND cover classes + E_CT on egg features only
#   era 2    7 charts, from 2020-01-20  SIGRID-3 SGD_* fields incl. SGD_POLY_T (I/L/W)
#   era 3   25 charts, from 2020-03-09  plain SIGRID-3 CT/POLY_TYPE — the sgrdr schema
#
# E_CT is the egg-code DISPLAY form — tenths as bare digits, plus '9+' and '10' — and it
# COLLIDES with SIGRID-3: '10' here means 10/10, where SIGRID-3 '10' means 1/10. Reusing
# CONCENTRATION_FRACTION on it would silently turn compact ice into a trace, and would not
# raise, because '10' is a valid key in both. So the tables below translate GEC_H to the
# SIGRID-3 codes the production conversion already understands, rather than introducing a
# second fraction table with its own drift.
#
# Values are exactly those observed across all 1,028 in-window charts (181,237 polygons);
# anything else raises rather than passing silently.

GEC_H_ROOT = Path("/home/eliedl/data/OGSL")

GEC_CT_TO_SIGRID3: dict[str, str] = {
    "0.": "00",                                        # 9 occurrences archive-wide; malformed '0'
    "1": "10", "2": "20", "3": "30", "4": "40", "5": "50",
    "6": "60", "7": "70", "8": "80", "9": "90",
    "9+": "91",                                        # 0.97 (DEC-015)
    "10": "92",                                        # 1.00
}

# Era-1 classes that carry no egg code. Fast ice is 40 % of all era-1 polygons, so this
# row carries real weight: it is read as consolidated 10/10 per MANICE.
# [NEEDS REVIEW] — the Fast ice and Bergy water rows are domain assumptions, not measured.
GEC_LEGEND_TO_SIGRID3: dict[str, str | None] = {
    "Fast ice": "92",       # consolidated fast ice -> 10/10
    "Open water": "00",
    "Ice free": "00",
    "Bergy water": "00",    # icebergs are not sea-ice concentration
    "Land": None,           # -> NaN, excluded from the fold
    "No data": None,
    "Egg": None,            # placeholder: these carry E_CT and are filled from it
    "Remote egg": None,
}

# The era-1 .prj sometimes declares "Not_specified_based_on_Clarke_1866_ellipsoid", which
# would reproject to 4326 with a null datum shift (~100-200 m error, i.e. 0.1-0.2 cell on
# this lattice). Clarke 1866 is NAD27's ellipsoid and the 2015+ charts say NAD27 outright,
# so an unspecified datum is pinned to NAD27 and the shift is applied properly.
GEC_H_CRS_NAD27 = ("+proj=lcc +lat_0=40 +lon_0=-100 +lat_1=49 +lat_2=77 "
                   "+x_0=0 +y_0=0 +datum=NAD27 +units=m +no_defs")


def gec_h_files() -> list[tuple[str, Path]]:
    """(YYYYMMDD, path) for every GEC_H chart in the climatology window, ascending."""
    start, end = Period(PERIOD).window
    lo, hi = start.replace("-", ""), end.replace("-", "")
    out = []
    for p in GEC_H_ROOT.glob("*/GEC_H_*.shp"):
        m = re.search(r"GEC_H_(\d{8})\.shp$", p.name)
        if m and lo <= m.group(1) < hi:
            out.append((m.group(1), p))
    return sorted(out)


# The SIGRID-3-schema eras, as (polygon-class column, CT code column). Measured across
# all 1,028 charts: SGD_-prefixed on 7 (from 2020-01-20), unprefixed on 25 (from
# 2020-03-09) — the latter is exactly the sgrdr schema.
GEC_SIGRID_COLUMNS = (("SGD_POLY_T", "SGD_CT"), ("POLY_TYPE", "CT"))
GEC_CLASS_COLUMNS = ("A_LEGEND", *(c for c, _ in GEC_SIGRID_COLUMNS))


def _gec_ct_codes(df) -> pd.Series:
    """One chart's polygons -> SIGRID-3 ``ct_code``, across GEC_H's three schemas."""
    for poly_col, ct_col in GEC_SIGRID_COLUMNS:
        if poly_col in df.columns:
            poly = df[poly_col].astype("string").str.strip()
            code = df[ct_col].astype("string").str.strip()
            # 'W' is open water at CT=0 and must enter the fold as a zero, exactly as the
            # sgrdr path does (DEC-009) and as era-1 'Open water' does; only 'L'/'N' are NaN.
            return code.where(poly == "I").mask(poly == "W", "00")

    if "A_LEGEND" not in df.columns:
        raise KeyError(f"GEC_H chart carries none of {GEC_CLASS_COLUMNS}")
    legend = df["A_LEGEND"].astype("string").str.strip()
    unknown = set(legend.dropna()) - set(GEC_LEGEND_TO_SIGRID3)
    if unknown:
        raise KeyError(f"unmapped GEC_H A_LEGEND class(es): {sorted(unknown)}")
    egg = df["E_CT"].astype("string").str.strip().replace("", pd.NA)
    unknown = set(egg.dropna()) - set(GEC_CT_TO_SIGRID3)
    if unknown:
        raise KeyError(f"unmapped GEC_H E_CT value(s): {sorted(unknown)}")
    # egg code wins where present; otherwise the cover class supplies the concentration
    return egg.map(GEC_CT_TO_SIGRID3).fillna(legend.map(GEC_LEGEND_TO_SIGRID3))


def load_gec_h_polygons(_sql: str = "") -> pd.DataFrame:
    """Drop-in for ``load_polygons``: MPO's GEC_H archive instead of the sgrdr table.

    Same contract — a frame carrying ``geometry`` (EPSG:4326) and ``obs_date`` plus the
    ``ct_code`` the production conversion consumes. Charts too broken to carry attributes
    at all are skipped and counted.
    """
    frames, skipped, dropped = [], [], 0
    for stamp, path in gec_h_files():
        # The archive carries some degenerate rings (2-point LinearRings) and inverted
        # winding orders. on_invalid="ignore" nulls the unreadable ones instead of raising;
        # they are dropped and counted rather than silently tolerated.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            g = gpd.read_file(path, on_invalid="ignore")
        if not set(GEC_CLASS_COLUMNS) & set(g.columns):
            skipped.append(stamp)                       # e.g. 20190822: FID only
            continue
        bad = g.geometry.isna() | g.geometry.is_empty
        if bad.any():
            dropped += int(bad.sum())
            g = g.loc[~bad]
        if g.crs is None or g.crs.to_epsg() is None and "Not_specified" in str(g.crs):
            g = g.set_crs(GEC_H_CRS_NAD27, allow_override=True)
        g = g.to_crs(epsg=4326)
        frames.append(pd.DataFrame({
            "geometry": g.geometry.to_numpy(),
            "obs_date": pd.Timestamp(stamp).date(),
            "ct_code": _gec_ct_codes(g).to_numpy(),
        }))
    if skipped:
        print(f"  GEC_H: skipped {len(skipped)} attribute-less chart(s): {skipped}")
    if dropped:
        print(f"  GEC_H: dropped {dropped:,} unreadable geometries across {len(frames)} charts")
    return pd.concat(frames, ignore_index=True)


def mpo_reduce(per_season: np.ndarray, *, offset: float = 0.0,
               scale: float = 1.0) -> np.ndarray:
    """The MPO statistic: sum over ice seasons / a FIXED N_SEASONS; ice-free seasons contribute 0."""
    out = np.nansum((per_season - offset) * scale, axis=0) / N_SEASONS
    out[np.sum(~np.isnan(per_season), axis=0) == 0] = np.nan   # never any ice -> absent from the file
    return out


def gated_mean_reduce(per_season: np.ndarray, *, offset: float = 0.0,
                      scale: float = 1.0) -> np.ndarray:
    """Gate first, then average: mean over the seasons that HAVE ice, only where >= MPO_GATE of them do.

    The literal reading of Galbraith 2026-08-17 — "le DOY moyen des 30 ans pour les
    pixels avec un minimum de 15 annees de presence de glace" — as a real mean over the
    contributing seasons rather than a fixed-30 denominator. Differs from ``mpo_reduce``
    on both counts: the denominator is n_valid, not 30, and sub-gate cells are dropped
    rather than diluted.
    """
    n_valid = np.sum(~np.isnan(per_season), axis=0)
    out = np.full(per_season.shape[1], np.nan, dtype=np.float32)
    keep = n_valid >= MPO_GATE
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Mean of empty slice")
        out[keep] = np.nanmean((per_season[:, keep] - offset) * scale, axis=0)
    return out


# Candidate cross-season statistics, selected with --reduce.
MPO_REDUCERS = {"sum30": mpo_reduce, "gated_mean": gated_mean_reduce}


def strictly_above(t: float) -> float:
    """The CT field is discrete, so ``> t`` is exactly ``>= the next representable code``."""
    return next(f for f in sorted(set(CONCENTRATION_FRACTION.values())) if f > t)


def candidates(prepared, tier: Tier, *, strict: bool, reduce: str = "sum30") -> dict[str, np.ndarray]:
    """The identified reduction, folded with the production kernels over the shared stream.

    ``strict`` swaps the occurrence test from ``CT >= 1/10`` to ``CT > 1/10``.
    ``ThresholdDate`` hardcodes ``>=``, so the strict form is expressed by raising
    the threshold to the next code (0.10 -> 0.20); ``ThresholdDuration`` takes the
    operator directly. Both spell the same predicate.
    """
    thr = strictly_above(CT_THRESHOLD) if strict else CT_THRESHOLD
    stream = lambda: _stream_day_stacks(prepared, tier=tier)
    first = ThresholdDate((thr,), "first_above").reduce(stream)
    last = ThresholdDate((thr,), "last_above").reduce(stream)
    dur = ThresholdDuration((CT_THRESHOLD,),
                            operator.gt if strict else operator.ge).reduce(stream)
    reduce_fn = MPO_REDUCERS[reduce]
    n_years = np.sum(~np.isnan(first), axis=0).astype(np.float32)
    if reduce == "gated_mean":
        n_years[n_years < MPO_GATE] = np.nan     # one footprint across all four maps
    return {
        "first_doy": reduce_fn(first, offset=DOY_OFFSET),
        "last_doy": reduce_fn(last, offset=DOY_OFFSET),
        "duration_d": reduce_fn(dur, scale=WEEK_DAYS),
        "n_years": n_years,
    }


# --- Phase C: cell-for-cell delta on the shared lattice ------------------------

def _score(delta: pd.Series, label: str, unit: str = "d") -> str:
    d = delta.dropna()
    return (f"  {label:12s} bias {d.mean():+7.3f} {unit} | median|Δ| {d.abs().median():6.3f}"
            f" | p95|Δ| {d.abs().quantile(0.95):6.3f} | |Δ|<=0.05: {(d.abs() <= 0.05).mean() * 100:5.1f}%"
            f" | |Δ|<=1: {(d.abs() <= 1).mean() * 100:5.1f}% | n {len(d):,}")


def scorecard(cmp: pd.DataFrame, n_seasons: int, n_days: int) -> list[str]:
    lines = [
        "Phase C — cell-for-cell on the .dat's own lattice (no resampling either side)",
        f"  cells {len(cmp):,} | seasons {n_seasons} | HDs {n_days}",
        f"  cells the file fills but we leave empty: "
        f"{cmp['ours_first_doy'].isna().mean() * 100:.3f}%",
        "",
    ]
    for col, unit in (("first_doy", "d"), ("last_doy", "d"),
                      ("duration_d", "d"), ("n_years", "yr")):
        lines.append(_score(cmp["ours_" + col] - cmp[col], col, unit))
    lines.append(f"  n_years exact: {(cmp.ours_n_years == cmp.n_years).mean() * 100:.2f}%")
    lines.append("")
    lines.append("  first_doy residual by N band:")
    for lo, hi in ((1, 9), (10, 14), (15, 19), (20, 29), (30, 30)):
        sel = (cmp.n_years >= lo) & (cmp.n_years <= hi)
        if not sel.any():
            continue
        d = (cmp.loc[sel, "ours_first_doy"] - cmp.loc[sel, "first_doy"]).dropna()
        lines.append(f"    N {lo:2d}-{hi:2d}: bias {d.mean():+7.3f} d"
                     f" | median|Δ| {d.abs().median():6.3f} | n {len(d):,}")
    return lines


# Quantity -> (unit, what the value is). n_years is a plain count: no threshold-then-sum/30
# dilution behind it, which is exactly why its residual isolates disagreement about
# *whether* a season had ice from disagreement about *when*.
DELTA_FIELDS = {
    "first_doy":  ("d", "threshold → sum over ice seasons / fixed 30"),
    "last_doy":   ("d", "threshold → sum over ice seasons / fixed 30"),
    "duration_d": ("d", "threshold → sum over ice seasons / fixed 30"),
    "n_years":    ("yr", "count of seasons with an occurrence — undiluted"),
}


def _scatter(vec: np.ndarray, tier: Tier) -> np.ndarray:
    """Wet-cell vector -> the lattice's (H, W) grid, NaN off the footprint."""
    grid = np.full((tier.grid.height, tier.grid.width), np.nan, dtype=np.float32)
    grid[tier.wet_mask] = vec
    return grid


def _map_axes(tier: Tier):
    """Geographic frame plus the flat-gray 'no value here' underlay every map shares."""
    xmin, ymin, xmax, ymax = tier.grid.bounds
    fig, ax = plt.subplots(figsize=(11, 7), dpi=150)
    ax.set_facecolor("#EEF1F3")
    ax.imshow(np.where(tier.wet_mask, 1.0, np.nan), extent=(xmin, xmax, ymin, ymax),
              cmap="Greys", vmin=0, vmax=3, interpolation="nearest")
    ax.set_aspect(1 / np.cos(np.deg2rad(float(np.mean([ymin, ymax])))))
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    return fig, ax, (xmin, xmax, ymin, ymax)


def delta_png(delta_vec: np.ndarray, tier: Tier, *, label: str, path: Path,
              unit: str = "d", note: str = "", source: str = "") -> None:
    """Map of (ours − theirs) on the shared lattice: diverging, gray where either side is silent."""
    delta = _scatter(delta_vec, tier)
    finite = delta[np.isfinite(delta)]
    # Full data range, no clipping. vmin/vmax are the true extremes; vcenter pins the
    # colormap's neutral to Δ=0 so the two hues keep meaning sign on an asymmetric range.
    vmin, vmax = float(finite.min()), float(finite.max())
    norm = (colors.TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
            if vmin < 0 < vmax else colors.Normalize(vmin=vmin, vmax=vmax))

    fig, ax, extent = _map_axes(tier)
    im = ax.imshow(delta, extent=extent, cmap="RdBu_r", norm=norm, interpolation="nearest")
    d = pd.Series(finite)
    ax.set_title(f"{label}: ours − MPO  |  bias {d.mean():+.3f} {unit}, "
                 f"median|Δ| {d.abs().median():.3f} {unit}, n {len(d):,}"
                 + (f"\n{textwrap.fill(source, 96)}" if source else "")
                 + (f"\n{textwrap.fill(note, 96)}" if note else ""), fontsize=10)
    fig.colorbar(im, ax=ax, shrink=0.8,
                 label=f"ours − MPO ({unit}) — full range {vmin:.2f} .. {vmax:.2f}")
    fig.tight_layout()
    fig.savefig(path, dpi=SAVE_DPI)
    plt.close(fig)


def field_png(values: np.ndarray, tier: Tier, *, label: str, path: Path,
              vmin: float, vmax: float, unit: str = "", note: str = "",
              source: str = "", contours: tuple[float, ...] = ()) -> None:
    """Map of an absolute field. Sequential single hue — a magnitude, not a signed residual.

    ``vmin``/``vmax`` are passed in rather than taken from the data so the scale stays
    absolute and comparable between runs (for n_years it is the record length, 0-30).
    ``contours`` draws labelled isolines over the fill.
    """
    grid = _scatter(values, tier)
    finite = grid[np.isfinite(grid)]
    fig, ax, extent = _map_axes(tier)
    im = ax.imshow(grid, extent=extent, cmap="YlGnBu", vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    if contours:
        xmin, xmax, _ymin, ymax = extent
        lons = xmin + (np.arange(grid.shape[1]) + 0.5) * LON_RES
        lats = ymax - (np.arange(grid.shape[0]) + 0.5) * LAT_RES
        levels = sorted(contours)
        # weight rises with the level so the outermost isoline — the one bounding the
        # agreement region — reads as primary; a lone level takes that weight outright
        widths = np.linspace(0.6, 1.6, len(levels)) if len(levels) > 1 else [1.6]
        cs = ax.contour(lons, lats, grid, levels=levels, colors="#12232B",
                        linewidths=widths, alpha=0.9)
        ax.clabel(cs, fmt=lambda v: f"{v:g}{unit}", fontsize=7, inline=True)
    ax.set_title(f"{label}  |  median {np.median(finite):.3g}{unit}, n {len(finite):,}"
                 + (f"\n{textwrap.fill(source, 96)}" if source else "")
                 + (f"\n{textwrap.fill(note, 96)}" if note else ""), fontsize=10)
    cb = fig.colorbar(im, ax=ax, shrink=0.8, label=f"{label}{unit}")
    if vmax - vmin == N_SEASONS:                      # integer count: label every 5 seasons
        cb.set_ticks(np.arange(vmin, vmax + 1, 5))
    fig.tight_layout()
    fig.savefig(path, dpi=SAVE_DPI)
    plt.close(fig)


# --- Inspect: one cell's whole CT matrix, for forensics on a large residual ----

def cell_series(lon: float, lat: float) -> pd.DataFrame:
    """CT time series of the polygons covering one point — the same cell the burn resolves.

    ``burn_ids`` assigns a cell from the polygon containing its centre, and the .dat's
    coordinates *are* the cell centres, so point-in-polygon here reproduces the burn.
    """
    start, end = Period(PERIOD).window
    sql = f"""
        SELECT ST_AsBinary(geometry) AS geom_wkb, "T1"::date AS obs_date, "CT" AS ct_code
        FROM sgrdr
        WHERE ST_Contains(geometry, ST_SetSRID(ST_Point({lon}, {lat}), 4326))
          AND "T1" >= '{start}' AND "T1" < '{end}'
        ORDER BY obs_date;
    """
    return METRICS["first_occurrence_date"].conversion.prepare(
        attach_season_calendar(load_polygons(sql)))


def _ct_glyph(v: float) -> str:
    """One character per CT: '.' open water, 1-9 tenths, '#' >= 9+/compact, ' ' no chart or no CT code."""
    if v is None or not np.isfinite(v):
        return " "
    if v <= 0:
        return "."
    if v >= 0.95:
        return "#"
    return str(int(round(v * 10)))


def inspect_cell(lon: float, lat: float, theirs: float, ours: float) -> list[str]:
    """Print one cell's season x day CT matrix and the arithmetic the .dat's value implies."""
    df = cell_series(lon, lat)
    dup = int(df.duplicated(["season", "day_of_season"]).sum())
    mat = df.pivot_table(index="season", columns="day_of_season", values="ct", aggfunc="last")
    days, seasons = list(mat.columns), list(mat.index)

    lines = [
        f"  cell ({lon:.4f}, {lat:.4f}) | .dat first_doy {theirs:+.2f} | ours {ours:+.2f}"
        f" | Δ {ours - theirs:+.2f} d",
        f"  matrix {len(seasons)} seasons x {len(days)} HDs"
        + (f" | WARNING {dup} duplicate (season, day) rows — overlapping polygons" if dup else ""),
        "",
        "        " + "".join("|" if d % 28 < 7 else " " for d in days) + "   crossing",
    ]
    per = []
    for s in seasons:
        row = mat.loc[s]
        hit = [d for d in days if np.isfinite(row[d]) and row[d] >= CT_THRESHOLD]
        first = hit[0] if hit else None
        per.append(first)
        lines.append(f"  {s}  " + "".join(_ct_glyph(row[d]) for d in days)
                     + ("   " + f"{first - DOY_OFFSET:+.0f}" if first is not None else "   —"))

    got = [d - DOY_OFFSET for d in per if d is not None]
    s_ours, s_theirs = float(np.sum(got)), theirs * N_SEASONS
    lines += [
        "",
        f"  seasons with ice {len(got)}/{len(seasons)} | summed DOY ours {s_ours:+.0f}"
        f" | implied by the .dat {s_theirs:+.1f} | difference {s_theirs - s_ours:+.1f} d"
        f" = {(s_theirs - s_ours) / 7:+.2f} HD weeks",
        f"  per-season crossings (signed DOY): {got}",
        "",
    ]
    return lines


# Absolute scales for --field. n_years is a count out of the record length, so its scale is
# fixed rather than data-driven and stays comparable between runs.
FIELD_LIMITS: dict[str, tuple[float, float, str]] = {
    "n_years": (0.0, float(N_SEASONS), " seasons"),
}


def field_mode(name: str, tag: str | None) -> list[str]:
    """Render our absolute field, rebuilt from the cached delta plus the .dat's own column.

    ``delta = ours - theirs``, so adding the file's column back inverts it exactly. That is
    lossless only where the cached delta is finite; any cell the delta dropped cannot be
    recovered, so those are counted and reported rather than passed off as data.
    """
    cache, delta_vec = _newest_delta(name, tag)
    mpo = load_mpo()
    tier, dat_idx = dat_tier(mpo)
    theirs = _theirs_on_wet(mpo[name].to_numpy(), dat_idx, tier)
    ours = delta_vec + theirs
    unrecoverable = int((np.isnan(delta_vec) & ~np.isnan(theirs)).sum())

    lo, hi, unit = FIELD_LIMITS.get(
        name, (float(np.nanmin(ours)), float(np.nanmax(ours)), ""))
    png = OUT / cache.name.replace(f"_delta_{name}.npy", f"_field_{name}.png")
    field_png(ours, tier, label=f"{name} (ours)", path=png, vmin=lo, vmax=hi, unit=unit,
              source=_source_label("gec_h" if tag and "gech" in tag else "sgrdr",
                                   f"run {cache.name.split('_delta_')[0]}"),
              note=f"rebuilt from {cache.name} + the .dat's own {name}")
    return [
        f"Field — {name} | cache {cache.name}",
        f"  cells {int(np.isfinite(ours).sum()):,} of {len(ours):,}"
        f" | range {np.nanmin(ours):.3g} .. {np.nanmax(ours):.3g} | scale {lo:g}..{hi:g}",
        f"  cells the delta could not recover: {unrecoverable:,}"
        + ("  (reconstruction is exact)" if unrecoverable == 0 else "  <-- rendered as no-value"),
        f"  wrote {png.name}",
    ]


SAVE_DPI = 300          # output resolution for every figure this probe writes

# Provenance shown on every figure. Which chart archive a map came from changes what its
# residual means, so it belongs on the figure rather than only in the filename.
SOURCE_LABELS = {
    "sgrdr": "sgrdr — CIS SIGRID-3 weekly charts, normalized on ingestion",
    "gec_h": "GEC_H — MPO's own SGRDREC archive, read from shapefiles",
}


def _source_label(source: str, extra: str = "") -> str:
    """One-line provenance for a figure title."""
    return f"{SOURCE_LABELS[source]} · {PERIOD} · vs IceGridOccurrence.GEC" + (
        f" · {extra}" if extra else "")

EXPERIMENT_OUT = OUT / "experiment"

# Isoline on the dilution map: 7 d, one HD week — the smallest step the weekly record can
# express, so inside it the two conventions are indistinguishable at the source's own
# resolution. That boundary is the whole question, so it is drawn alone rather than nested
# among tighter lines that only restate the fill.
DILUTION_ISOLINES = (7.0,)


def dilution_map(name: str = "first_doy", tag_sum: str = "ge_gech",
                 tag_gated: str = "ge_gech_gated") -> list[str]:
    """Paint every cell with the median ``gated_mean − sum30`` offset for its .dat N band.

    The two reducers differ by exactly the denominator ratio (``gated = sum30 × 30/N``), so
    this renders the dilution the fixed-30 divisor imposes as a function of how often a cell
    actually carries ice — the same quantity as the per-N table, laid out spatially. Cells
    below the gate have no gated value at all and stay blank.

    ``theirs`` cancels in the difference, so nothing here depends on reconstruction.
    """
    _, d_sum = _newest_delta(name, tag_sum)
    _, d_gat = _newest_delta(name, tag_gated)
    mpo = load_mpo()
    tier, idx = dat_tier(mpo)
    n_years = _theirs_on_wet(mpo.n_years.to_numpy(), idx, tier)
    diff = d_gat - d_sum

    offset = np.full(len(n_years), np.nan, dtype=np.float32)
    rows = []
    for n in range(1, N_SEASONS + 1):
        band = n_years == n
        seen = band & np.isfinite(diff)
        if not seen.any():
            continue
        med = float(np.median(diff[seen]))
        offset[band] = med                    # the whole band, not just the cells that scored
        rows.append((n, int(band.sum()), med))

    EXPERIMENT_OUT.mkdir(parents=True, exist_ok=True)
    png = EXPERIMENT_OUT / f"dilution_offset_{name}.png"
    field_png(offset, tier, label=f"median (gated_mean − sum30) by N — {name}", path=png,
              vmin=0.0, vmax=float(np.nanmax(offset)), unit=" d",
              source=_source_label("gec_h", f"{tag_gated} minus {tag_sum}"),
              contours=DILUTION_ISOLINES,
              note=f"each cell carries its N band's median offset; N < {MPO_GATE} stays blank. "
                   f"Inside the {DILUTION_ISOLINES[-1]:g} d isoline the two conventions agree "
                   f"to within one HD week, the finest step the weekly record resolves.")
    inside = int((offset < DILUTION_ISOLINES[-1]).sum())
    painted = int(np.isfinite(offset).sum())
    return [
        f"Dilution offset — {name} | {tag_gated} minus {tag_sum}",
        f"  bands with a gated value: {len(rows)} | cells painted {painted:,} of {len(offset):,}",
        f"  inside the {DILUTION_ISOLINES[-1]:g} d isoline (agreement within one HD week): "
        f"{inside:,} cells = {100 * inside / painted:.1f}% of those painted",
        *(f"    N {n:>2}  cells {c:>7,}  median offset {m:+7.3f} d" for n, c, m in rows),
        f"  wrote {png.relative_to(OUT.parent)}",
    ]


PATCH_MIN_DELTA = 2.0    # |Δ| (d) a cell must carry to join a patch — just under p99 (2.70)
PATCH_MIN_CELLS = 200    # cells a same-sign blob must span to count as a patch, not speckle
PATCH_INTERIOR = 3       # cells of clearance from the footprint edge, to exclude the coastal band


def _newest_delta(name: str = "first_doy", tag: str | None = None) -> tuple[Path, np.ndarray]:
    """Newest cached delta for ``name``, restricted to a run ``tag`` when given.

    Without a tag this resolves to whichever run wrote last, which silently crosses
    sources once more than one has run — pass the tag (``ge``, ``ge_gech``, ...) to pin it.
    """
    hits = sorted(OUT.glob(f"*_{tag}_delta_{name}.npy" if tag else f"*_delta_{name}.npy"))
    if not hits:
        raise FileNotFoundError(f"no cached delta for {name!r}"
                                + (f" with tag {tag!r}" if tag else "")
                                + f" under {OUT}")
    return hits[-1], np.load(hits[-1])


def find_patches(n: int, tag: str | None = None) -> list[str]:
    """Largest same-sign, in-basin blobs of |Δ| — the coherent residuals that are not coastline."""
    from scipy import ndimage

    cache, delta_vec = _newest_delta("first_doy", tag)
    mpo = load_mpo()
    tier, dat_idx = dat_tier(mpo)
    wet = tier.wet_mask

    delta = np.full(wet.shape, np.nan, np.float32)
    delta[wet] = delta_vec
    # in-basin = at least PATCH_INTERIOR cells clear of any lattice position the .dat leaves empty,
    # so the 2008-coastline band (probe 006 eras) cannot masquerade as an interior patch
    interior = ndimage.distance_transform_edt(wet) >= PATCH_INTERIOR

    lines = [f"Patches — cache {cache.name}",
             f"  |Δ| >= {PATCH_MIN_DELTA} d, >= {PATCH_MIN_CELLS} cells, "
             f">= {PATCH_INTERIOR} cells from the footprint edge", ""]
    found = []
    for sign, label in ((+1, "ours later"), (-1, "ours earlier")):
        sel = interior & np.isfinite(delta) & (delta * sign >= PATCH_MIN_DELTA)
        lab, count = ndimage.label(sel)
        for i in range(1, count + 1):
            cells = lab == i
            size = int(cells.sum())
            if size < PATCH_MIN_CELLS:
                continue
            rows, cols = np.nonzero(cells)
            k = int(np.argmax(np.abs(delta[rows, cols])))   # representative = strongest residual
            x, y = (tier.grid.transform * (cols[k] + 0.5, rows[k] + 0.5))
            found.append({"size": size, "label": label, "mask": cells,
                          "mean": float(delta[cells].mean()), "peak": float(delta[rows[k], cols[k]]),
                          "lon": float(x), "lat": float(y),
                          "lo": float(np.nanmin(delta[cells])), "hi": float(np.nanmax(delta[cells]))})
    found.sort(key=lambda p: -p["size"])
    top = found[:n]
    for i, p in enumerate(top, start=1):
        lines.append(f"  [{i:>2d}] {p['size']:>6,} cells | {p['label']:12s} | mean Δ {p['mean']:+7.2f} d"
                     f" | range {p['lo']:+.2f}..{p['hi']:+.2f}"
                     f" | peak {p['peak']:+7.2f} d at ({p['lon']:.4f}, {p['lat']:.4f})")
    if not top:
        lines.append("  none")
        return lines
    png = OUT / f"{cache.name.replace('_delta_first_doy.npy', '')}_patches.png"
    patches_png(delta, tier, top, path=png)
    lines += ["", f"  wrote {png.name}"]
    return lines


def patches_png(delta: np.ndarray, tier: Tier, patches: list[dict], *, path: Path) -> None:
    """Locator map: the residual field with each patch outlined and its inspected cell marked.

    Deliberately clipped to a few times the patch threshold — this map answers "where are
    they", not "how large"; the unclipped delta maps carry the magnitudes.
    """
    lim = PATCH_MIN_DELTA * 2
    xmin, ymin, xmax, ymax = tier.grid.bounds
    lons = xmin + (np.arange(tier.grid.width) + 0.5) * LON_RES
    lats = ymax - (np.arange(tier.grid.height) + 0.5) * LAT_RES

    fig, ax = plt.subplots(figsize=(11, 7), dpi=150)
    ax.set_facecolor("#EEF1F3")
    ax.imshow(np.where(tier.wet_mask, 1.0, np.nan), extent=(xmin, xmax, ymin, ymax),
              cmap="Greys", vmin=0, vmax=3, interpolation="nearest")
    im = ax.imshow(delta, extent=(xmin, xmax, ymin, ymax), cmap="RdBu_r",
                   vmin=-lim, vmax=lim, interpolation="nearest")
    for i, p in enumerate(patches, start=1):
        ax.contour(lons, lats, p["mask"].astype(float), levels=[0.5],
                   colors="#111111", linewidths=0.9)
        ax.plot(p["lon"], p["lat"], "o", mfc="none", mec="#111111", ms=13, mew=1.6)
        ax.annotate(str(i), (p["lon"], p["lat"]), textcoords="offset points", xytext=(11, 7),
                    fontsize=9, fontweight="bold", color="#111111")
    ax.set_aspect(1 / np.cos(np.deg2rad(float(np.mean([ymin, ymax])))))
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title(f"first_doy residual — {len(patches)} largest in-basin patches "
                 f"(|Δ| ≥ {PATCH_MIN_DELTA} d, ≥ {PATCH_MIN_CELLS} cells, "
                 f"≥ {PATCH_INTERIOR} cells off the coast)\n"
                 f"circle = the cell inspected for that patch", fontsize=10)
    fig.colorbar(im, ax=ax, shrink=0.8, label=f"ours − MPO (days) — clipped to ±{lim:g} for locating")
    fig.tight_layout()
    fig.savefig(path, dpi=SAVE_DPI)
    plt.close(fig)


def inspect_at(lon: float, lat: float, tag: str | None = None) -> list[str]:
    """Inspect one named cell, pairing it with the .dat row and the cached residual."""
    cache, delta_vec = _newest_delta("first_doy", tag)
    mpo = load_mpo()
    _tier, dat_idx = dat_tier(mpo)
    r = int(((mpo.lon - lon).abs() + (mpo.lat - lat).abs()).idxmin())
    theirs = float(mpo.first_doy.iloc[r])
    return [f"Inspect — cache {cache.name}", ""] + inspect_cell(
        float(mpo.lon.iloc[r]), float(mpo.lat.iloc[r]),
        theirs, theirs + float(delta_vec[dat_idx[r]]))


def inspect_sample(n: int, tag: str | None = None) -> list[str]:
    """Dump the CT matrix of the first n cells whose first_doy |Δ| exceeds the median |Δ|."""
    cache, delta = _newest_delta("first_doy", tag)
    mpo = load_mpo()
    _tier, dat_idx = dat_tier(mpo)
    finite = np.isfinite(delta)
    med = float(np.median(np.abs(delta[finite])))
    above = np.flatnonzero(finite & (np.abs(delta) > med))

    row_of = np.empty(len(dat_idx), dtype=np.int64)   # wet-cell index -> .dat row (a bijection)
    row_of[dat_idx] = np.arange(len(dat_idx))

    lines = [f"Inspect — cache {cache.name}",
             f"  median|Δ| {med:.3f} d | {len(above):,} of {int(finite.sum()):,} cells above it", ""]
    for w in above[:n]:
        r = int(row_of[w])
        theirs = float(mpo.first_doy.iloc[r])
        lines += inspect_cell(float(mpo.lon.iloc[r]), float(mpo.lat.iloc[r]),
                              theirs, theirs + float(delta[w]))
    return lines


def _theirs_on_wet(values: np.ndarray, dat_idx: np.ndarray, tier: Tier) -> np.ndarray:
    """Scatter one of the .dat's own columns into wet-vector order (one row per wet cell)."""
    out = np.full(int(tier.wet_mask.sum()), np.nan, dtype=np.float32)
    out[dat_idx] = values
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reduce", choices=tuple(MPO_REDUCERS), default="sum30",
                    help="cross-season statistic: sum over ice seasons / fixed 30 (default), "
                         f"or mean over contributing seasons gated at N >= {MPO_GATE}")
    ap.add_argument("--source", choices=("sgrdr", "gec_h"), default="sgrdr",
                    help="chart source: the normalized sgrdr table, or MPO's own GEC_H archive")
    ap.add_argument("--strict", action="store_true",
                    help=f"occurrence test CT > {CT_THRESHOLD} instead of CT >= {CT_THRESHOLD}")
    ap.add_argument("--tag", default=None, metavar="TAG",
                    help="pin the cache-reading modes to one run's tag (ge, ge_gech, "
                         "ge_gech_gated, ...); default is whichever run wrote last")
    ap.add_argument("--field", choices=tuple(DELTA_FIELDS), default=None,
                    help="skip the full pass; map our absolute field, rebuilt from the "
                         "cached delta plus the .dat's own column")
    ap.add_argument("--dilution-map", action="store_true",
                    help="skip the full pass; map the median (gated_mean − sum30) offset per "
                         "N band into output/experiment/")
    ap.add_argument("--patches", type=int, metavar="N", default=0,
                    help="skip the full pass; list + map the N largest same-sign in-basin |Δ| "
                         "patches from the newest cached first_doy delta")
    ap.add_argument("--at", metavar="LON,LAT", default=None,
                    help="skip the full pass; dump the CT matrix of the cell nearest this point")
    ap.add_argument("--inspect", type=int, metavar="N", default=0,
                    help="skip the full pass; dump the CT matrix of the first N cells whose "
                         "first_doy |Δ| exceeds the median, from the newest cached delta")
    args = ap.parse_args()

    if args.dilution_map:
        print("\n".join(dilution_map()))
        return
    if args.field:
        print("\n".join(field_mode(args.field, args.tag)))
        return
    if args.patches:
        print("\n".join(find_patches(args.patches, args.tag)))
        return
    if args.at:
        lon, lat = (float(v) for v in args.at.split(","))
        print("\n".join(inspect_at(lon, lat, args.tag)))
        return
    if args.inspect:
        print("\n".join(inspect_sample(args.inspect, args.tag)))
        return

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    tag = ("gt" if args.strict else "ge") + ("_gech" if args.source == "gec_h" else "") \
        + ("_gated" if args.reduce == "gated_mean" else "")
    test = (f"CT > {CT_THRESHOLD} (i.e. CT >= {strictly_above(CT_THRESHOLD)}, the next code)"
            if args.strict else f"CT >= {CT_THRESHOLD}")
    lines = [f"Probe 027 — {stamp} | {test} | {PERIOD} | source {args.source}"
             f" | .dat-native lattice", ""]

    mpo = load_mpo()
    lines += decode_checks(mpo)

    tier, dat_idx = dat_tier(mpo)
    lines.append(f"  lattice {tier.grid.height} x {tier.grid.width} @ "
                 f"{LON_RES} x {LAT_RES} deg | .dat cells {int(tier.wet_mask.sum()):,}")
    print(lines[-1])

    prepared = fetch_prepared(tier, source=args.source)
    n_seasons, n_days = prepared["season"].nunique(), prepared["day_of_season"].nunique()
    print(f"prepared rows {len(prepared):,} | seasons {n_seasons} | HDs {n_days}")

    ours = candidates(prepared, tier, strict=args.strict, reduce=args.reduce)
    cmp = mpo[["first_doy", "last_doy", "duration_d", "n_years"]].copy()
    if args.reduce == "gated_mean":
        # Our reducer already drops sub-gate cells; blank the same cells on the .dat side so
        # the diff is symmetric. Cells where the two disagree about crossing the gate fall
        # out as NaN and are counted by the "file fills but we leave empty" line.
        below = cmp.n_years < MPO_GATE
        cmp.loc[below, list(DELTA_FIELDS)] = np.nan
        lines.append(f"  gated_mean: blanked {int(below.sum()):,} .dat cells with N < {MPO_GATE}"
                     f" ({below.mean() * 100:.1f}%)")
    for name, vec in ours.items():
        cmp["ours_" + name] = vec[dat_idx]
    lines += ["", *scorecard(cmp, n_seasons, n_days)]

    for name, (unit, note) in DELTA_FIELDS.items():
        delta = ours[name] - _theirs_on_wet(cmp[name].to_numpy(), dat_idx, tier)
        # cached in wet-cell order (tier.wet_mask scatters it back) so the maps can be
        # re-rendered or re-examined without another DB pass
        npy = OUT / f"{stamp}_{tag}_delta_{name}.npy"
        np.save(npy, delta)
        png = OUT / f"{stamp}_{tag}_delta_{name}.png"
        delta_png(delta, tier, label=name, path=png, unit=unit, note=note,
                  source=_source_label(args.source, f"run {stamp}_{tag}"))
        print(f"wrote {npy.name}, {png.name}")

    (OUT / f"{stamp}_{tag}.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
