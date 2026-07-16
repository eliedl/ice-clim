"""Probe 027 — TTM (MPO conventions) validation against IceGridOccurrence GEC.

Reproduces the MPO IceGridOccurrence climatology (GEC, 1991-2020, weekly SGRDREC
charts — `~/data/MPO/`, format per P. Galbraith 2026-07-09) with the pipeline's
own kernels folded over `_stream_day_stacks` (threshold-then-<reducer>, DEC-049),
then compares per MPO grid point on the golfe∩GEC intersection:

  first-ice DOY   <- nanmean over ice seasons of ThresholdDate(0.1, first_above)
  last-ice DOY    <- nanmean over ice seasons of ThresholdDate(0.1, last_above)
  duration (days) <- candidates from ThresholdDuration(0.1) x 7 d/week:
                       A: mean over observed seasons (ice-free seasons count 0)
                       B: sum / n_seasons (never-observed seasons count 0)
                       C: bracket nanmean(last - first) over ice seasons
  N (years w/ ice) <- n_valid = count of seasons with a first-ice crossing

The cross-season MEAN is probe-local (staged promotion): it enters
`reductions.py` as the TTM reducer only if this validation passes (DEC-049).
Phase A decodes the `.dat` internally (duration-vs-bracket census, `00-00`
sentinel, N census) before any DB work.

Conversions: our day-of-season (Sep-1 anchored) - 121 = MPO signed Jan-1 DOY
(Dec 2 -> -29, matches the file's minimum); `.dat` longitudes are positive-west.

No write-back; reads the `.dat` and the `sgrdr` table read-only.
Output: timestamped txt scorecard + scatter PNG under output/.

Run:
    .venv/bin/python -m backend.probes.027_ttm_mpo_validation.probe
"""

from __future__ import annotations

import operator
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from rasterio.transform import rowcol

load_dotenv(Path(__file__).parents[3] / ".env")

from climatology.processing.metrics import METRICS
from climatology.processing.reductions import (
    ThresholdDate,
    ThresholdDuration,
    _stream_day_stacks,
)
from climatology.processing.regions import resolve_region
from climatology.services.sources import CHART_TABLES
from climatology.services.db import load_polygons
from climatology.services.temporal import Period, assert_hd_aligned, attach_season_calendar

DAT = Path("/home/eliedl/data/MPO/IceGridOccurrence.GEC.climatology.dat")
OUT = Path(__file__).parent / "output"
TARGET_CRS = 32198
PERIOD = "1991-2020"
CT_THRESHOLD = 0.1   # occurrence threshold (MPO README: CT >= 1/10)
DOY_OFFSET = 121     # day_of_season (Sep-1 anchored) - 121 = signed Jan-1 DOY
WEEK_DAYS = 7.0      # weekly HD cadence -> observation-weeks to days


# --- Phase A: file-internal decode checks ------------------------------------

def load_mpo() -> gpd.GeoDataFrame:
    """`.dat` -> GeoDataFrame(32198); longitude stored positive-west."""
    cols = ["lon_w", "lat", "first_doy", "first_dt", "last_doy", "last_dt",
            "duration_d", "n_years"]
    df = pd.read_csv(DAT, sep=r"\s+", header=None, names=cols,
                     dtype={"first_dt": str, "last_dt": str})
    return gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(-df["lon_w"], df["lat"]), crs="EPSG:4326",
    ).to_crs(f"EPSG:{TARGET_CRS}")


def decode_checks(mpo: gpd.GeoDataFrame) -> list[str]:
    """Internal-consistency census of the MPO file (no DB)."""
    gap = mpo.duration_d - (mpo.last_doy - mpo.first_doy)
    sent = mpo.last_dt.eq("00-00")
    return [
        "Phase A — .dat decode checks",
        f"  rows {len(mpo):,} | N range {mpo.n_years.min()}-{mpo.n_years.max()}"
        f" | N==30: {(mpo.n_years == 30).mean() * 100:.1f}%",
        f"  duration - bracket(last-first): median {gap.median():+.2f} d"
        f" | > 0: {(gap > 1e-9).mean() * 100:.2f}% (cumulative reading expects <= 0)",
        f"  '00-00' sentinel rows: {sent.sum():,}"
        + (f" | their N values: {sorted(mpo.loc[sent, 'n_years'].unique())[:8]}" if sent.any() else ""),
        "",
    ]


# --- Phase B: reproduce with the pipeline's kernels --------------------------

def fetch_prepared(tier):
    """sgrdr rows for the golfe fetch domain over the 1991-2020 window, season-calendared and CT-converted."""
    spec = METRICS["first_occurrence_date"]
    clim_start, clim_end = Period(PERIOD).window
    sql = spec.sql(table=CHART_TABLES["sgrdr"].table, bbox_wkt=tier.fetch_wkt,
                   climatology_start_date=clim_start, climatology_end_date=clim_end)
    df = load_polygons(sql)
    assert_hd_aligned(df, source_slug="sgrdr")
    return spec.conversion.prepare(attach_season_calendar(df))


def per_season_folds(prepared, tier):
    """The real kernels folded over the shared day-stack stream: three (n_seasons, n_wet) results."""
    stream = lambda: _stream_day_stacks(prepared, tier=tier, value_cols=("ct",))
    first = ThresholdDate((CT_THRESHOLD,), "first_above").reduce(stream)
    last = ThresholdDate((CT_THRESHOLD,), "last_above").reduce(stream)
    dur = ThresholdDuration((CT_THRESHOLD,), operator.ge).reduce(stream)
    return first, last, dur


def mpo_style_aggregates(first, last, dur) -> dict[str, np.ndarray]:
    """Probe-local MPO reducer (staged promotion, DEC-049): cross-season nanmean + sum/30 dilution + duration candidates."""
    n_seasons = first.shape[0]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Mean of empty slice")
        out = {
            "ours_first": np.nanmean(first, axis=0) - DOY_OFFSET,
            "ours_last": np.nanmean(last, axis=0) - DOY_OFFSET,
            "ours_dur_A": np.nanmean(dur * WEEK_DAYS, axis=0),
            "ours_dur_C": np.nanmean(last - first, axis=0),
        }
    out["ours_dur_B"] = np.nansum(dur * WEEK_DAYS, axis=0) / n_seasons
    # dilution model: dates also summed over ice years / n_seasons (zeros for
    # iceless years), like the duration — N=1 cells' near-Jan-1 dates suggest it
    out["ours_first_d30"] = np.nansum(first - DOY_OFFSET, axis=0) / n_seasons
    out["ours_last_d30"] = np.nansum(last - DOY_OFFSET, axis=0) / n_seasons
    out["ours_n"] = np.sum(~np.isnan(first), axis=0).astype(np.float32)
    return out


# --- Phase C: point-wise comparison ------------------------------------------

def sample_at_points(mpo: gpd.GeoDataFrame, tier, wet_vectors: dict) -> pd.DataFrame:
    """MPO points -> nearest golfe wet cell; returns aligned MPO + ours columns."""
    g = tier.grid
    r, c = rowcol(g.transform, mpo.geometry.x.values, mpo.geometry.y.values)
    r, c = np.asarray(r), np.asarray(c)
    inb = (r >= 0) & (r < g.height) & (c >= 0) & (c < g.width)
    idx_grid = np.full((g.height, g.width), -1, dtype=np.int64)
    idx_grid[tier.wet_mask] = np.arange(int(tier.wet_mask.sum()))
    widx = np.full(len(mpo), -1, dtype=np.int64)
    widx[inb] = idx_grid[r[inb], c[inb]]
    ok = widx >= 0
    out = mpo.loc[ok, ["first_doy", "last_doy", "duration_d", "n_years"]].reset_index(drop=True)
    for name, vec in wet_vectors.items():
        out[name] = vec[widx[ok]]
    return out


def _score(delta: pd.Series, label: str, unit: str = "d") -> str:
    d = delta.dropna()
    return (f"  {label:26s} mean bias {d.mean():+7.2f} {unit} | median|Δ| {d.abs().median():6.2f}"
            f" | p95|Δ| {d.abs().quantile(0.95):6.2f} | |Δ|<=3.5: {(d.abs() <= 3.5).mean() * 100:5.1f}%"
            f" | n {len(d):,}")


def scorecard(cmp: pd.DataFrame, n_seasons: int, n_days: int) -> list[str]:
    lines = [
        "Phase C — point-wise comparison (golfe ∩ GEC, nearest wet cell)",
        f"  MPO points matched to a wet cell: {len(cmp):,}"
        f" | seasons {n_seasons} | admissible HDs {n_days}",
        f"  cells where ours has no event (NaN) but MPO does: "
        f"{cmp['ours_first'].isna().mean() * 100:.2f}%",
        "",
        _score(cmp.ours_first - cmp.first_doy, "first-ice DOY (mean)"),
        _score(cmp.ours_first_d30 - cmp.first_doy, "first-ice DOY (sum/30)"),
        _score(cmp.ours_last - cmp.last_doy, "last-ice DOY (mean)"),
        _score(cmp.ours_last_d30 - cmp.last_doy, "last-ice DOY (sum/30)"),
        _score(cmp.ours_dur_A - cmp.duration_d, "duration A (mean obs x7)"),
        _score(cmp.ours_dur_B - cmp.duration_d, "duration B (sum/30 x7)"),
        _score(cmp.ours_dur_C - cmp.duration_d, "duration C (bracket mean)"),
        _score(cmp.ours_n - cmp.n_years, "N years with ice", unit="yr"),
        f"  N exact match: {(cmp.ours_n == cmp.n_years).mean() * 100:.1f}%",
        "",
        "  first-ice bias by MPO N (mean model vs sum/30 dilution model):",
    ]
    for lo, hi in ((30, 30), (20, 29), (10, 19), (1, 9)):
        sub = cmp[(cmp.n_years >= lo) & (cmp.n_years <= hi)]
        if sub.empty:
            continue
        bias_mean = (sub.ours_first - sub.first_doy).mean()
        bias_d30 = (sub.ours_first_d30 - sub.first_doy).mean()
        lines.append(f"    N {lo:2d}-{hi:2d}: mean {bias_mean:+7.2f} d"
                     f" | sum/30 {bias_d30:+7.2f} d | n {len(sub):,}")
    return lines


def plot(cmp: pd.DataFrame, png: Path) -> None:
    panels = [("first_doy", "ours_first", "first-ice DOY"),
              ("last_doy", "ours_last", "last-ice DOY"),
              ("duration_d", "ours_dur_A", "duration (cand. A, days)"),
              ("n_years", "ours_n", "N years with ice")]
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), dpi=140)
    for ax, (mpo_col, ours_col, label) in zip(axes.ravel(), panels):
        sub = cmp[[mpo_col, ours_col]].dropna()
        hb = ax.hexbin(sub[mpo_col], sub[ours_col], gridsize=80, bins="log", cmap="viridis")
        lo = min(sub[mpo_col].min(), sub[ours_col].min())
        hi = max(sub[mpo_col].max(), sub[ours_col].max())
        ax.plot([lo, hi], [lo, hi], "r-", lw=0.8)
        ax.set_xlabel(f"MPO {label}")
        ax.set_ylabel(f"ours {label}")
        fig.colorbar(hb, ax=ax, shrink=0.8)
    fig.suptitle(f"Probe 027 — TTM (mean, CT>={CT_THRESHOLD}) vs IceGridOccurrence GEC {PERIOD}")
    fig.tight_layout()
    fig.savefig(png)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    mpo = load_mpo()
    lines = [f"Probe 027 — {stamp} | threshold CT>={CT_THRESHOLD} | period {PERIOD}", ""]
    lines += decode_checks(mpo)

    tier = resolve_region("golfe").tiers[0]
    prepared = fetch_prepared(tier)
    n_seasons = prepared["season"].nunique()
    n_days = prepared["day_of_season"].nunique()
    print(f"prepared rows {len(prepared):,} | seasons {n_seasons} | admissible HDs {n_days}")

    first, last, dur = per_season_folds(prepared, tier)
    cmp = sample_at_points(mpo, tier, mpo_style_aggregates(first, last, dur))
    lines += scorecard(cmp, n_seasons, n_days)

    png = OUT / f"{stamp}_scatter.png"
    plot(cmp, png)
    (OUT / f"{stamp}.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"wrote {png.name}")


if __name__ == "__main__":
    main()
