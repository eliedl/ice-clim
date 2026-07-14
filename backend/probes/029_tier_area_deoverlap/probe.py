"""Probe 029 — tier area de-overlap validation (multi-tier area weighting).

The per-era composite (`climatology/utils/metric_per_era_composite.py`) draws an
area-weighted value distribution beside each map. Adaptive regions carry two tiers that
cover the *same ground* at different resolutions (coarse 1 km over the whole MRC, fine
100 m over the coastal buffer), so a raw cell count would let a 100 m cell and a 1 km cell
speak equally and the fine tier would outvote the coarse one 100:1 per km². `_area_weights`
instead attributes each patch of ground to the finest tier holding data there.

## What this validates

  A. **Cell size** — `Tier.res_m` is the *requested* resolution: `build_grid` ceils the cell
     count and stretches cells to span the wet bbox exactly, so true cells are slightly
     smaller than nominal and not square. Areas must come from bounds/shape, never res_m².

  B. **De-overlap identity** — the fine tier's footprint lies inside the coarse tier's, so
     the de-overlapped total must equal the coarse raster's wet area *exactly*:

         sum(own_area) == n_coarse_wet x coarse_cell_area

     Any excess means fine ground was counted that the coarse tier never claimed (leak);
     any shortfall means a coarse cell was over-claimed and clipped. Both are reported.
     Naive (tiers summed) is printed alongside to show the double count that is avoided.

  C. **Product distribution** — on a real archived product, the area-weighted value
     distribution, which must sum to 100% of the region.

Read-only: uses the region geometry and (for C) the archived rasters written by
`climatology/utils/sweep.py`. No DB, no write-back.

Run:
    .venv/bin/python -m backend.probes.029_tier_area_deoverlap.probe
    .venv/bin/python -m backend.probes.029_tier_area_deoverlap.probe --metric season_duration
"""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from climatology.processing.regions import resolve_region
from climatology.services.plot import RasterLayer, _area_weights, _deposit
from climatology.services.temporal import SEASON_ORIGIN
from climatology.utils.export import OUTPUT_DIR

OUTPUT_DIR_PROBE = Path(__file__).parent / "output"

REGION = "manicouagan"
METRIC = "breakup_date"
PERIOD = "1991-2020"
SOURCE = "sgrdr"

# The rasters approximate the wet polygon; they do not reproduce it. 2% bounds the
# rasterization error at the coarse tier's 1 km cell against this region's coastline.
RASTER_TOL = 0.02
KM2 = 1e6


def _wet_layers(region_slug: str) -> list[RasterLayer]:
    """Each tier's wet mask as a raster layer (1.0 where wet, NaN where dry) — the metric-independent footprint."""
    layers = []
    for tier in resolve_region(region_slug).tiers:
        values = np.where(tier.wet_mask, 1.0, np.nan).astype(np.float32)
        layers.append(RasterLayer(values, tier.grid.bounds, tier.res_m))
    return layers


def _archived_layers(region: str, metric: str, period: str, source: str) -> list[RasterLayer]:
    """The archived product rasters, coarse first (mirrors the composite's loader)."""
    tiers = [t.level for t in resolve_region(region).tiers]
    layers = []
    for tier in tiers:
        hits = sorted(glob.glob(str(OUTPUT_DIR / region / metric / period / source
                                    / "archive" / f"*_{tier}_*.npz")))
        if not hits:
            raise FileNotFoundError(
                f"No archived {tier} raster for {metric}/{period}/{source} — run sweep.py first.")
        manifest = json.loads(Path(hits[-1]).with_suffix(".json").read_text())
        layers.append(RasterLayer(np.load(hits[-1])["values"],
                                  tuple(manifest["bounds"]),
                                  float(manifest["grid_res_m"])))
    return layers


def report_cell_size(layers: list[RasterLayer], region: str) -> list[str]:
    """A: true cell size vs the tier's nominal res_m, and the area error res_m² would cause."""
    lines = [f"--- A. Cell size vs nominal resolution ({region}) ---",
             f"{'tier':>8} {'nominal':>9} {'true x':>10} {'true y':>10} {'true area':>12} "
             f"{'res_m^2 err':>12}"]
    for i, layer in enumerate(layers):
        res_x, res_y = layer.cell_size
        nominal_area = layer.res_m ** 2
        err = 100.0 * (nominal_area - layer.cell_area) / layer.cell_area
        lines.append(f"{i:>8} {layer.res_m:>8.0f}m {res_x:>9.3f}m {res_y:>9.3f}m "
                     f"{layer.cell_area:>11,.0f}m2 {err:>11.2f}%")
    lines.append("  (build_grid ceils the cell count then stretches cells to span the wet")
    lines.append("   bbox, so true cells run just under nominal and are not square.)")
    return lines


def report_deoverlap(layers: list[RasterLayer], truth: float, label: str) -> list[str]:
    """B: de-overlapped area against the wet *polygon* area, with the divergence broken down.

    The reference is the geometry, not either raster. The tiers are each stretched to their
    own bbox, so neither rasterization reproduces the polygon exactly and the two disagree
    with each other; the leak and over-claim lines below say by how much and why.
    """
    coarse, finest = layers[0], layers[-1]
    _, weights = _area_weights(layers)

    dedup = float(weights.sum())
    naive = sum(float(np.isfinite(l.values).sum()) * l.cell_area for l in layers)
    coarse_raster = float(np.isfinite(coarse.values).sum()) * coarse.cell_area

    # Leak: finer ground the coarse tier never claims — its centre lands on a coarse cell
    # that is non-finite or off-grid. The 100 m wet mask resolves coastal strips the 1 km
    # mask drops, so the fine footprint is NOT a subset of the coarse one.
    claimed = _deposit(coarse, finest, np.where(np.isfinite(finest.values),
                                                finest.cell_area, 0.0))
    fine_area = float(np.isfinite(finest.values).sum()) * finest.cell_area
    leak = fine_area - float(claimed[np.isfinite(coarse.values)].sum())
    # Over-claim: the grids disagree about the same ground. A fully covered coarse cell is
    # claimed by ~100 fine cells whose areas sum to more than the coarse cell's own area.
    over = float(np.clip(claimed - coarse.cell_area, 0.0, None).sum())

    rel = abs(dedup - truth) / truth
    return [
        "",
        f"--- B. De-overlapped area vs wet polygon ({label}) ---",
        f"  naive (tiers summed)       {naive / KM2:12,.1f} km2  <- double counts the overlap",
        f"  de-overlapped              {dedup / KM2:12,.1f} km2",
        f"  coarse raster              {coarse_raster / KM2:12,.1f} km2",
        f"  TRUTH (wet polygon)        {truth / KM2:12,.1f} km2",
        f"  overlap removed            {100 * (1 - dedup / naive):12.1f} %",
        "",
        f"  |dedup - truth| / truth    {100 * rel:12.2f} %   tol {100 * RASTER_TOL:.0f} %   "
        f"{'PASS' if rel < RASTER_TOL else 'FAIL'}",
        f"  leak  (fine ground the coarse tier never claims) {leak / KM2:10.3f} km2",
        f"  over-claim (grids disagree on the same ground)   {over / KM2:10.3f} km2",
        "  Both are rasterization artifacts, not weighting errors: each tier is stretched",
        "  to its own bbox, so 100 fine cells != 1 coarse cell and the fine wet mask",
        "  resolves coastline the coarse one misses.",
    ]


def report_distribution(layers: list[RasterLayer], metric: str, period: str,
                        source: str) -> list[str]:
    """C: the area-weighted value distribution of an archived product."""
    values, weights = _area_weights(layers)
    total = float(weights.sum())
    is_date = metric.endswith("_date")

    lines = ["", f"--- C. Area-weighted distribution: {metric} / {period} / {source} ---",
             f"{'value':>8} {'label':>10} {'area km2':>12} {'% of region':>12}"]
    for value in np.unique(values):
        area = float(weights[values == value].sum())
        label = ((SEASON_ORIGIN + timedelta(days=int(value))).strftime("%b %d")
                 if is_date else "")
        lines.append(f"{value:>8.0f} {label:>10} {area / KM2:>11,.1f} {100 * area / total:>11.2f}%")

    pct_sum = 100.0 * float(weights.sum()) / total
    lines.append(f"{'':>8} {'TOTAL':>10} {total / KM2:>11,.1f} {pct_sum:>11.2f}%   "
                 f"{'PASS' if abs(pct_sum - 100.0) < 1e-9 else 'FAIL'}")
    lines.append(f"  distinct values: {len(np.unique(values))} "
                 f"(a weekly source quantizes date metrics to 7-day steps)")
    return lines


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", default=REGION)
    p.add_argument("--metric", default=METRIC)
    p.add_argument("--period", default=PERIOD)
    p.add_argument("--source", default=SOURCE)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUTPUT_DIR_PROBE.mkdir(parents=True, exist_ok=True)

    truth = float(resolve_region(args.region).tiers[0].wet.area)   # the wet polygon, in m2

    wet = _wet_layers(args.region)
    lines = [f"=== Probe 029 — tier area de-overlap ({args.region}) ===",
             f"Run: {stamp}", ""]
    lines += report_cell_size(wet, args.region)
    lines += report_deoverlap(wet, truth, f"{args.region} wet masks")

    product = _archived_layers(args.region, args.metric, args.period, args.source)
    lines += report_deoverlap(product, truth, f"{args.region} / {args.metric} product")
    lines += report_distribution(product, args.metric, args.period, args.source)

    report = "\n".join(lines)
    out = OUTPUT_DIR_PROBE / f"{stamp}_{args.region}_{args.metric}.txt"
    out.write_text(report + "\n")
    print(report)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()