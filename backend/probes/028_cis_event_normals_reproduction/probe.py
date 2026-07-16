"""Probe 028 — CIS 1991-2020 event-normals reproduction scorecard (Sept-Îles).

Generalizes the probe-010 comparison from one product to the CIS event-normals
family: every published 1991-2020 EC normal that our metric registry already
reproduces is recomputed through the production pipeline on one shared
RunContext spec (sept-iles / sgrdr / 1991-2020 / mtt) and diff-mapped, cell by
cell, against its CIS counterpart on the tier grid.

    ours : METRICS[<slug>] via RunContext -> _fetch -> _compute_tiers
    CIS  : the product's MMDD week class -> the same Sep-1-anchored
           day-of-season ordinal (services.temporal.SEASON_ORIGIN)
    diff : ours - CIS (days; positive = ours later)

Five products, one descriptor row each (PRODUCTS); the compare engine is
product-agnostic. The per-HD weekly fields (ctmed/cpmed/pimed/prmed/
icfrq/oifrq/fifrq) are a different shape — cross-season reductions that keep
the day axis — and are out of scope here.

Window caveat: each CIS product is only defined on its own weekly window
(e.g. freeze-up Dec 4 - Mar 12). Our kernels search the full admissible season,
so a crossing outside that window is representable for us and structurally not
for CIS. The scorecard counts those cells separately rather than silently
folding them into the bias.

Rasters are cached per product under output/; pass --recompute to rebuild from
the DB.

Run:
    .venv/bin/python -m backend.probes.028_cis_event_normals_reproduction.probe
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.pipeline import RunContext, _compute_tiers, _fetch  # noqa: E402
from climatology.processing.metrics import METRICS  # noqa: E402
from climatology.processing.rasterize import GRID_CRS, Grid, burn_values  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402
from climatology.services.sources import CHART_TABLES  # noqa: E402
from climatology.services.temporal import SEASON_ORIGIN, Period, day_of_season  # noqa: E402

CIS_ROOT = Path("/home/eliedl/data/CIS/1991-2020_climatology_shapefiles/EC")
OUTPUT_DIR = Path(__file__).parent / "output"

REGION = "sept-iles"
SOURCE = "sgrdr"
PERIOD = "1991-2020"
REDUCTION = "mtt"

# CIS weekly quantization: the bands the agreement rates are keyed to.
AGREEMENT_BANDS_D = (3.5, 7.0, 14.0)


@dataclass(frozen=True)
class CisProduct:
    """One published CIS normal and the metric that should reproduce it."""

    metric_slug: str
    shp: Path
    column: str        # the MMDD week-class column in that shapefile
    label: str         # scorecard / plot title

    @property
    def name(self) -> str:
        return self.shp.stem


PRODUCTS: tuple[CisProduct, ...] = (
    CisProduct("freeze_up_date", CIS_ROOT / "freezeup/freeze.shp", "freeze",
               "freeze-up (CT>=4/10)"),
    CisProduct("breakup_date", CIS_ROOT / "breakup/break.shp", "break",
               "break-up (CT>=4/10)"),
    CisProduct("first_occurrence_date", CIS_ROOT / "freezeup/first.shp", "first",
               "first ice (CT>=1/10)"),
    CisProduct("last_occurrence_date", CIS_ROOT / "breakup/last.shp", "last",
               "last ice (CT>=1/10)"),
    CisProduct("landfast_freeze_up_date", CIS_ROOT / "fast_ice/fifup.shp", "fifup",
               "fast-ice freeze-up (FA='08')"),
)


# --- ours: the production pipeline on one shared RunContext spec -------------

def compute_ours(product: CisProduct, region, *, recompute: bool) -> np.ndarray:
    """The metric's raster through the production pipeline (cached per product)."""
    cache = OUTPUT_DIR / f"ours_{product.metric_slug}.npy"
    if cache.exists() and not recompute:
        print(f"  cached: {cache.name}")
        return np.load(cache)
    ctx = RunContext(metric=METRICS[product.metric_slug],
                     source=CHART_TABLES[SOURCE], region=region, period=Period(PERIOD))
    values = _compute_tiers(_fetch(ctx), ctx)[-1].values
    np.save(cache, values)
    print(f"  computed + cached: {cache.name}")
    return values


# --- CIS: week classes -> day-of-season ordinals on our grid -----------------

def rasterize_cis(product: CisProduct, grid: Grid) -> np.ndarray:
    """Burn a CIS product's MMDD week classes onto the tier grid as ordinals.

    Non-date classes are dropped so they stay NaN rather than burning a bogus
    ordinal: '0' is the climate-normals landmask / no-event class (DEC-034) and
    'L' appears as an explicit land class in break.shp.
    """
    cis = gpd.read_file(product.shp).to_crs(GRID_CRS)
    weeks = cis[product.column].astype(str)
    dated = cis[weeks.str.fullmatch(r"\d{4}")].copy()
    dated["ordinal"] = (dated[product.column].astype(str)
                        .map(lambda s: day_of_season(f"{s[:2]}-{s[2:]}")))
    return burn_values(list(zip(dated.geometry, dated["ordinal"])), grid)


# --- scorecard ---------------------------------------------------------------

def fmt_day(d: float) -> str:
    return (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")


def score(product: CisProduct, ours: np.ndarray, cis: np.ndarray) -> list[str]:
    """One product's agreement block: coverage, signed bias, weekly-band rates."""
    diff = ours - cis
    both = np.isfinite(ours) & np.isfinite(cis)
    ours_only = np.isfinite(ours) & ~np.isfinite(cis)
    cis_only = ~np.isfinite(ours) & np.isfinite(cis)

    lines = [f"=== {product.metric_slug}  vs  {product.name}.shp  ({product.label})"]
    if not both.any():
        return lines + ["  no cell defined in both rasters — nothing to compare", ""]

    d = diff[both]
    lo, hi = np.nanmin(cis), np.nanmax(cis)
    # Cells whose crossing we place outside the CIS product's own weekly window
    # are unrepresentable for CIS by construction — a window effect, not a bias.
    outside = int(((ours[both] < lo) | (ours[both] > hi)).sum())

    lines += [
        f"  cells both defined {int(both.sum()):>8,} | ours-only {int(ours_only.sum()):>7,}"
        f" | CIS-only {int(cis_only.sum()):>7,}",
        f"  exact agreement    {100 * (d == 0).mean():>7.2f}%"
        f" | ours outside the CIS window ({fmt_day(lo)}-{fmt_day(hi)}): {outside:,}",
        f"  ours - CIS (days)  median {np.median(d):+.1f} | mean {d.mean():+.1f}"
        f" | std {d.std():.1f} | p05 {np.percentile(d, 5):+.1f}"
        f" | p95 {np.percentile(d, 95):+.1f}",
        "  agreement vs the CIS weekly quantization: "
        + " | ".join(f"|Δ|<={b:g}d {100 * (np.abs(d) <= b).mean():.1f}%"
                     for b in AGREEMENT_BANDS_D),
        f"  range  ours {fmt_day(np.nanmin(ours))}-{fmt_day(np.nanmax(ours))}"
        f" | CIS {fmt_day(lo)}-{fmt_day(hi)}",
        "",
    ]
    return lines


def plot(product: CisProduct, ours: np.ndarray, cis: np.ndarray,
         bounds, stamp: str) -> Path:
    """Four-panel diff map: ours, CIS, signed difference, difference histogram."""
    diff = ours - cis
    both = np.isfinite(ours) & np.isfinite(cis)
    xmin, ymin, xmax, ymax = bounds
    extent = [xmin, xmax, ymin, ymax]

    vmin = np.nanmin([np.nanmin(ours), np.nanmin(cis)])
    vmax = np.nanmax([np.nanmax(ours), np.nanmax(cis)])
    dmax = np.nanpercentile(np.abs(diff[both]), 99) if both.any() else 1.0
    dmax = max(dmax, 1.0)

    fig, axes = plt.subplots(2, 2, figsize=(16, 13))
    for ax, arr, title, cmap, kw in [
        (axes[0, 0], ours, f"UQAR {product.metric_slug} ({SOURCE}, {PERIOD}, {REDUCTION})",
         "viridis", dict(vmin=vmin, vmax=vmax)),
        (axes[0, 1], cis, f"CIS normals ({product.name}.shp)", "viridis",
         dict(vmin=vmin, vmax=vmax)),
        (axes[1, 0], diff, "UQAR - CIS (days; red = ours later)", "RdBu_r",
         dict(vmin=-dmax, vmax=dmax)),
    ]:
        im = ax.imshow(arr, origin="upper", extent=extent, cmap=cmap,
                       interpolation="none", **kw)
        ax.set_title(title)
        ax.ticklabel_format(style="plain", axis="both")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        if cmap == "viridis":
            ticks = np.linspace(vmin, vmax, 6)
            cbar.set_ticks(ticks)
            cbar.set_ticklabels([fmt_day(t) for t in ticks], fontsize=8)

    ax = axes[1, 1]
    if both.any():
        d = diff[both]
        ax.hist(d, bins=np.arange(np.floor(d.min()) - 0.5, np.ceil(d.max()) + 1.5, 1),
                color="#4878d0", edgecolor="none")
        ax.axvline(0, color="k", linewidth=0.8)
        for w in (-7, 7):
            ax.axvline(w, color="gray", linewidth=0.8, linestyle="--")
    ax.set_xlabel("UQAR - CIS (days); dashes = ±1 CIS week")
    ax.set_ylabel("cells")
    ax.set_title("Difference distribution")

    fig.suptitle(f"Probe 028 — {product.label}: UQAR vs CIS 1991-2020 normals, "
                 f"{REGION} (EPSG:{GRID_CRS})", fontsize=13)
    png = OUTPUT_DIR / f"{stamp}_{product.metric_slug}.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true",
                    help="Rebuild the UQAR rasters from the DB instead of the cache.")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    region = resolve_region(REGION)
    grid = region.tiers[-1].grid

    lines = [
        "=== Probe 028 — CIS event-normals reproduction scorecard ===",
        f"Generated: {stamp}",
        f"RunContext: region={REGION} | source={SOURCE} | period={PERIOD} | reduction={REDUCTION}",
        f"Grid: {grid.width} x {grid.height} @ EPSG:{GRID_CRS} ({region.tiers[-1].res_m:g} m)",
        "Difference = ours - CIS (days; positive = ours later)",
        "",
    ]
    for product in PRODUCTS:
        print(f"{product.metric_slug} vs {product.name}.shp")
        ours = compute_ours(product, region, recompute=args.recompute)
        cis = rasterize_cis(product, grid)
        lines += score(product, ours, cis)
        plot(product, ours, cis, grid.bounds, stamp)

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print("\n" + report)
    print(f"Saved: {OUTPUT_DIR / f'{stamp}.txt'} (+ {len(PRODUCTS)} PNGs)")


if __name__ == "__main__":
    main()
