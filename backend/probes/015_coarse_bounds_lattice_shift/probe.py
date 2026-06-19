"""Probe 015 — Coarse-tier grid lattice shift from the DEC-041 bounds trim.

Quantifies *why* the DEC-041 coarse `bounds_geom` trim (region -> coastal/water
zone) reproduces the old region-bbox product only to ~99 % rather than 100 %.

A raster is a lattice pinned to its bbox top-left corner `(xmin, ymax)`, with
cell centres at `xmin+(j+0.5)·cellw, ymax-(i+0.5)·cellh` where `cellw =
(xmax-xmin)/ceil((xmax-xmin)/res)` (build_grid). Trimming `bounds_geom` changes
the bbox, hence the **origin** and the **effective cell size**, so the new
lattice's cell centres land at different ground points than the old one's. The
climatology samples each cell by the chart polygon at its centre (DEC-035), so
cells whose centre sits within ~½ cell of a weekly freeze-up isochron can flip
to the neighbouring HD-week (±7 d) — a one-cell fringe along the isochrons.

This probe compares, for an adaptive region, the OLD coarse envelope
(`tiers[0].clip_geom` = the whole region, the pre-DEC-041 `bounds_geom`) against
the NEW one (`tiers[0].bounds_geom` = the trimmed coastal/water domain), and
reports the **integer vs fractional origin shift** (the fractional part is what
causes the fringe), the **cell-size mismatch** (‰), and its accumulated drift.

No DB access; geometry only.

Run:
    .venv/bin/python -m backend.probes.015_coarse_bounds_lattice_shift.probe [slug]
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from climatology.processing.rasterize import build_grid  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"


def _grid(env, res: float):
    """(xmin, ymax, width, height, cellw, cellh) for build_grid of ``env``."""
    _, h, w, (xmin, ymin, xmax, ymax) = build_grid(env, res)
    return xmin, ymax, w, h, (xmax - xmin) / w, (ymax - ymin) / h


def run(slug: str = "manicouagan") -> None:
    spec = resolve_region(slug)
    t0 = spec.tiers[0]
    if t0.clip_geom is None:
        sys.exit(f"{slug}: legacy region (clip_geom=None) — no DEC-041 trim to compare.")
    res = float(t0.res_m)

    # OLD = pre-DEC-041 coarse bounds_geom (the whole region, still tiers[0].clip_geom);
    # NEW = DEC-041 trimmed coarse bounds_geom (region - inland land beyond buffer).
    oxmin, oymax, ow, oh, ocw, och = _grid(t0.clip_geom, res)
    nxmin, nymax, nw, nh, ncw, nch = _grid(t0.bounds_geom, res)

    dx_cells, dy_cells = (nxmin - oxmin) / res, (nymax - oymax) / res
    frac_x, frac_y = abs(dx_cells) % 1, abs(dy_cells) % 1
    ppt_x, ppt_y = (ncw - ocw) / res * 1e3, (nch - och) / res * 1e3
    drift_x, drift_y = abs(ncw - ocw) * nw / res, abs(nch - och) * nh / res  # cells across span

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    lines = [
        f"Probe 015 — coarse bounds lattice shift (DEC-041)  ({stamp})",
        f"region={slug}  grid_crs=EPSG:{spec.grid_crs}  res={res:g} m  (coarse tier)",
        "",
        f"OLD envelope (region)   origin xmin,ymax = {oxmin:.2f}, {oymax:.2f}  "
        f"| {ow}x{oh}  cell {ocw:.4f} x {och:.4f} m",
        f"NEW envelope (trimmed)  origin xmin,ymax = {nxmin:.2f}, {nymax:.2f}  "
        f"| {nw}x{nh}  cell {ncw:.4f} x {nch:.4f} m",
        "",
        f"origin shift : Δx = {nxmin-oxmin:,.2f} m = {dx_cells:.4f} cells "
        f"(integer {int(dx_cells)}, FRACTIONAL {frac_x:.3f})",
        f"               Δy = {nymax-oymax:,.2f} m = {dy_cells:.4f} cells "
        f"(integer {int(dy_cells)}, FRACTIONAL {frac_y:.3f})",
        f"cell-size    : Δcellw = {ncw-ocw:+.4f} m ({ppt_x:+.2f} ‰); "
        f"Δcellh = {nch-och:+.4f} m ({ppt_y:+.2f} ‰)",
        f"               accumulated drift across grid: {drift_x:.2f} cells (x), "
        f"{drift_y:.2f} cells (y)",
        "",
        "The integer part of the origin shift is harmless (whole-cell translation).",
        "The FRACTIONAL part (above) is the sub-cell phase offset that moves cell",
        "centres onto different ground points; with centroid sampling (DEC-035),",
        "cells within ~½ cell of a weekly freeze-up isochron flip by ±7 d — the",
        "one-cell fringe behind the ~99 % (not 100 %) regression reproducibility",
        "(DEC-041; climatology/tests/diff_map_regression_test.py).",
    ]
    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)

    # ---- Figure: bbox extents + zoomed cell-centre lattices (phase offset) ----
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(13, 6))
    for xmin, ymax, w, h, cw, ch, color, label in [
        (oxmin, oymax, ow, oh, ocw, och, "#7a828c", "OLD (region)"),
        (nxmin, nymax, nw, nh, ncw, nch, "#2c7", "NEW (trimmed)"),
    ]:
        ax0.add_patch(plt.Rectangle((xmin, ymax - h * ch), w * cw, h * ch,
                                    fill=False, edgecolor=color, lw=1.5, label=label))
    ax0.set_xlim(min(oxmin, nxmin) - 5e3, max(oxmin + ow * ocw, nxmin + nw * ncw) + 5e3)
    ax0.set_ylim(min(oymax - oh * och, nymax - nh * nch) - 5e3, max(oymax, nymax) + 5e3)
    ax0.set_aspect("equal"); ax0.legend(fontsize=8); ax0.set_title(f"{slug}: coarse envelopes (EPSG:{spec.grid_crs})")
    ax0.set_xlabel("Easting (m)"); ax0.set_ylabel("Northing (m)")

    # Zoom: cell centres of both grids in a small window near the NEW origin.
    x0, y0 = nxmin + 3 * ncw, nymax - 3 * nch
    n = 6
    for xmin, ymax, cw, ch, color, marker, label in [
        (oxmin, oymax, ocw, och, "#7a828c", "x", "OLD centres"),
        (nxmin, nymax, ncw, nch, "#2c7", "+", "NEW centres"),
    ]:
        js = range(int((x0 - xmin) / cw) - 1, int((x0 - xmin) / cw) + n)
        is_ = range(int((ymax - y0) / ch) - 1, int((ymax - y0) / ch) + n)
        xs = [xmin + (j + 0.5) * cw for j in js]
        ys = [ymax - (i + 0.5) * ch for i in is_]
        gx, gy = np.meshgrid(xs, ys)
        ax1.scatter(gx, gy, c=color, marker=marker, s=60, label=label)
    ax1.set_aspect("equal"); ax1.legend(fontsize=8)
    ax1.set_title(f"cell-centre lattices (phase offset {frac_x:.2f}, {frac_y:.2f} cell)")
    ax1.set_xlabel("Easting (m)"); ax1.set_ylabel("Northing (m)")
    fig.tight_layout()
    png = OUTPUT_DIR / f"{stamp}_lattice_shift.png"
    fig.savefig(png, dpi=150)
    print(f"\nSaved {png}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "manicouagan")
