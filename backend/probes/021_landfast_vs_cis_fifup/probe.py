"""Probe 021 — Landfast (CT=1.0 proxy) vs CIS fast-ice freeze-up normals.

External validation of the CT=1.0 fast-ice proxy (probe 019/020): differences
our proxy fast-ice freeze-up climatology against the published CIS 1991-2020 EC
fast-ice freeze-up normals (`fifup.shp`), on a common grid/time axis — the
probe-010 pattern, applied to fast ice.

  ours : EventDate(1.0, "first_above") on CT_CONVERSION — first HD whose median
         CT reaches 1.0 (compact ≈ fast ice), sgrdr winters 1991-2020.
  CIS  : fifup.shp `fifup` column — MMDD fast-ice-freeze-up week per polygon
         ('0' = climate-normals landmask / no fast ice), mapped to the same
         Sep-1-anchored day-of-season ordinal.

Difference = ours − CIS (days; positive = ours later). If small and unbiased,
the CT=1.0 proxy reproduces the authoritative fast-ice freeze-up climatology.

Usage:
    python probe.py [--recompute]
"""

from __future__ import annotations

import argparse
import operator
import sys
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.pipeline import RunContext, _compute_tiers, _fetch  # noqa: E402
from climatology.processing.metrics import EventDate, MetricSpec  # noqa: E402
from climatology.processing.rasterize import GRID_CRS, burn_values  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402
from climatology.processing.sources import CHART_TABLES  # noqa: E402
from climatology.services.temporal import SEASON_ORIGIN, Period, day_of_season  # noqa: E402
from climatology.services.units_conversion_maps import CT_CONVERSION  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"
OURS_CACHE = OUTPUT_DIR / "ours_values.npy"

FIFUP = Path("/home/eliedl/data/CIS/1991-2020_climatology_shapefiles/EC/fast_ice/fifup.shp")
REGION = "sept-iles"
SOURCE = "sgrdr"
PERIOD = "1991-2020"


def compute_ours(region, *, recompute: bool) -> np.ndarray:
    """Our CT=1.0 proxy fast-ice freeze-up raster through the pipeline (cached)."""
    if OURS_CACHE.exists() and not recompute:
        print(f"Using cached proxy raster: {OURS_CACHE} (pass --recompute to rebuild)")
        return np.load(OURS_CACHE)
    metric = MetricSpec(EventDate(1.0, "first_above"), fields=("CT",),
                        conversion=CT_CONVERSION)
    ctx = RunContext(metric=metric, source=CHART_TABLES[SOURCE], region=region,
                     period=Period(PERIOD))
    fetch = _fetch(ctx)
    values = _compute_tiers(fetch, ctx)[-1].values
    OUTPUT_DIR.mkdir(exist_ok=True)
    np.save(OURS_CACHE, values)
    print(f"Cached proxy raster: {OURS_CACHE}")
    return values


def rasterize_cis(grid) -> np.ndarray:
    """CIS fifup.shp MMDD freeze-up weeks -> day-of-season ordinals on our grid."""
    cis = gpd.read_file(FIFUP).to_crs(GRID_CRS)
    ice = cis[(cis["fifup"] != "0") & cis["fifup"].notna()].copy()
    ice["ordinal"] = ice["fifup"].map(lambda s: day_of_season(f"{s[:2]}-{s[2:]}"))
    return burn_values(list(zip(ice.geometry, ice["ordinal"])), grid)


def fmt_day(d: float) -> str:
    return (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")


def stats_report(ours, cis, diff) -> list[str]:
    both = np.isfinite(ours) & np.isfinite(cis)
    ours_only = np.isfinite(ours) & ~np.isfinite(cis)
    cis_only = ~np.isfinite(ours) & np.isfinite(cis)
    d = diff[both]
    return [
        f"Cells with both defined : {both.sum():,}",
        f"Cells proxy-only        : {ours_only.sum():,}  (compact but no CIS fast-ice normal)",
        f"Cells CIS-only          : {cis_only.sum():,}  (CIS fast ice, proxy never reaches 1.0)",
        "",
        "Signed difference (proxy - CIS, days; positive = ours later):",
        f"  median = {np.median(d):+.1f}   mean = {d.mean():+.1f}   std = {d.std():.1f}",
        f"  p05 = {np.percentile(d, 5):+.1f}   p25 = {np.percentile(d, 25):+.1f}   "
        f"p75 = {np.percentile(d, 75):+.1f}   p95 = {np.percentile(d, 95):+.1f}",
        "",
        "Agreement vs the CIS weekly quantization:",
        f"  |diff| <= 3.5 d (half-week) : {100 * (np.abs(d) <= 3.5).mean():.1f}%",
        f"  |diff| <= 7 d   (one week)  : {100 * (np.abs(d) <= 7).mean():.1f}%",
        f"  |diff| <= 14 d  (two weeks) : {100 * (np.abs(d) <= 14).mean():.1f}%",
        "",
        "Value ranges (day-of-season ordinals, Sep-1 anchored):",
        f"  proxy : {np.nanmin(ours):.0f}-{np.nanmax(ours):.0f} "
        f"({fmt_day(np.nanmin(ours))} - {fmt_day(np.nanmax(ours))})",
        f"  CIS   : {np.nanmin(cis):.0f}-{np.nanmax(cis):.0f} "
        f"({fmt_day(np.nanmin(cis))} - {fmt_day(np.nanmax(cis))})",
    ]


def plot(ours, cis, diff, bounds, stamp: str) -> Path:
    xmin, ymin, xmax, ymax = bounds
    extent = [xmin, xmax, ymin, ymax]
    both = np.isfinite(ours) & np.isfinite(cis)
    vmin = np.nanmin([np.nanmin(ours), np.nanmin(cis)])
    vmax = np.nanmax([np.nanmax(ours), np.nanmax(cis)])
    dmax = np.nanpercentile(np.abs(diff[both]), 99) if both.any() else 1.0

    fig, axes = plt.subplots(2, 2, figsize=(16, 13))
    for ax, arr, title, cmap, norm_kw in [
        (axes[0, 0], ours, f"proxy fast-ice freeze-up (CT>=1.0, sgrdr, {PERIOD})",
         "viridis", dict(vmin=vmin, vmax=vmax)),
        (axes[0, 1], cis, "CIS fast-ice freeze-up normals (fifup.shp)", "viridis",
         dict(vmin=vmin, vmax=vmax)),
        (axes[1, 0], diff, "proxy - CIS (days; red = ours later)", "RdBu_r",
         dict(vmin=-dmax, vmax=dmax)),
    ]:
        im = ax.imshow(arr, origin="upper", extent=extent, cmap=cmap,
                       interpolation="none", **norm_kw)
        ax.set_title(title)
        ax.ticklabel_format(style="plain", axis="both")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        if cmap == "viridis":
            ticks = np.linspace(vmin, vmax, 6)
            cbar.set_ticks(ticks)
            cbar.set_ticklabels([fmt_day(t) for t in ticks], fontsize=8)

    ax = axes[1, 1]
    d = diff[both]
    ax.hist(d, bins=np.arange(np.floor(d.min()) - 0.5, np.ceil(d.max()) + 1.5, 1),
            color="#4878d0", edgecolor="none")
    ax.axvline(0, color="k", linewidth=0.8)
    for w_ in (-7, 7):
        ax.axvline(w_, color="gray", linewidth=0.8, linestyle="--")
    ax.set_xlabel("proxy - CIS (days); dashes = ±1 CIS week")
    ax.set_ylabel("cells")
    ax.set_title("Difference distribution")
    fig.suptitle(f"Probe 021 — CT=1.0 proxy vs CIS fast-ice freeze-up, {REGION}, "
                 f"winters {PERIOD}", fontsize=13)
    png = OUTPUT_DIR / f"{stamp}_difference.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    return png


def main():
    ap = argparse.ArgumentParser(description="CT=1.0 proxy vs CIS fast-ice freeze-up.")
    ap.add_argument("--recompute", action="store_true", help="rebuild the proxy raster from the DB")
    args = ap.parse_args()

    region = resolve_region(REGION)
    grid = region.tiers[-1].grid
    ours = compute_ours(region, recompute=args.recompute)
    cis = rasterize_cis(grid)
    diff = ours - cis

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    lines = [
        "=== Probe 021 — CT=1.0 proxy vs CIS fast-ice freeze-up normals ===",
        f"Generated: {stamp}",
        f"Region: {REGION} | Source: {SOURCE} | Winters: {PERIOD} | CIS: fifup.shp",
        "",
        *stats_report(ours, cis, diff),
    ]
    report = "\n".join(lines)
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report)
    png = plot(ours, cis, diff, grid.bounds, stamp)
    print("\n" + report)
    print(f"\nSaved: {OUTPUT_DIR / f'{stamp}.txt'}\n       {png}")


if __name__ == "__main__":
    main()
