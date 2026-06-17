"""CRS-aware diff regression test for archived climatology products.

Compares two archived products, each a ``.npz`` (with a ``values`` array) plus a
sibling ``.json`` manifest carrying ``grid_crs``, ``bounds`` and ``grid_shape``.
The **first** product is the BASELINE (reference); the **second** is the
CANDIDATE. If the candidate's CRS / bounds / shape differ from the baseline's,
the candidate is **reprojected onto the baseline grid** before differencing.

This is the special-case tool for a refactor that *also* reprojects (e.g. the
26919→32198 migration, DEC-040): it confirms the science is unchanged at shared
physical locations. Resampling is **nearest-neighbour** — product values are
day-of-season ordinals (or counts); interpolation would invent non-representable
values (DEC-035). Coverage differences at the edges (one product's bbox smaller
than the other's — e.g. the 32198 axis-aligned bbox is smaller than the old
26919 MRR-square grid) are *expected* and reported separately from value
differences; they show up as a non-zero fringe.

Run:
    python -m climatology.tests.diff_map_regression_test BASELINE.npz CANDIDATE.npz

The ``.json`` metadata is the sibling file (same stem) of each ``.npz``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

OUTPUT_DIR = Path(__file__).parent / "output"


class Product:
    """An archived raster product + its georeferencing, from .npz + .json."""

    def __init__(self, npz_path: Path):
        self.npz_path = npz_path
        self.values = np.load(npz_path)["values"].astype("float32")
        meta = json.loads(npz_path.with_suffix(".json").read_text())
        self.crs = int(meta["grid_crs"])
        if "bounds" not in meta:
            raise KeyError(
                f"{npz_path.name}: manifest has no 'bounds' — cannot georeference. "
                "Re-archive with the bounds-carrying manifest, or backfill it."
            )
        self.bounds = tuple(float(b) for b in meta["bounds"])  # xmin,ymin,xmax,ymax
        h, w = self.values.shape
        self.transform = from_bounds(*self.bounds, w, h)
        self.label = npz_path.stem

    def aligned_to(self, ref: "Product") -> np.ndarray:
        """Candidate values resampled onto ``ref``'s grid (nearest, NaN-filled)."""
        same = (self.crs == ref.crs
                and np.allclose(self.bounds, ref.bounds)
                and self.values.shape == ref.values.shape)
        if same:
            return self.values
        dst = np.full(ref.values.shape, np.nan, dtype="float32")
        reproject(
            source=self.values, destination=dst,
            src_transform=self.transform, src_crs=f"EPSG:{self.crs}",
            dst_transform=ref.transform, dst_crs=f"EPSG:{ref.crs}",
            resampling=Resampling.nearest,
            src_nodata=np.nan, dst_nodata=np.nan,
        )
        return dst


def _stats(base: np.ndarray, cand: np.ndarray) -> dict:
    both = np.isfinite(base) & np.isfinite(cand)
    diff = cand - base
    d = diff[both]
    n = int(both.sum())
    return {
        "both_defined": n,
        "baseline_only": int((np.isfinite(base) & ~np.isfinite(cand)).sum()),
        "candidate_only": int((~np.isfinite(base) & np.isfinite(cand)).sum()),
        "exact_zero_pct": 100.0 * np.sum(d == 0) / n if n else float("nan"),
        "within_1_pct": 100.0 * np.sum(np.abs(d) <= 1) / n if n else float("nan"),
        "mean": float(np.mean(d)) if n else float("nan"),
        "std": float(np.std(d)) if n else float("nan"),
        "p95_abs": float(np.percentile(np.abs(d), 95)) if n else float("nan"),
        "max_abs": float(np.max(np.abs(d))) if n else float("nan"),
        "diff": diff, "both": both,
    }


def run(baseline_npz: Path, candidate_npz: Path) -> None:
    base = Product(baseline_npz)
    cand = Product(candidate_npz)
    reprojected = not (base.crs == cand.crs and np.allclose(base.bounds, cand.bounds)
                       and base.values.shape == cand.values.shape)
    cand_aligned = cand.aligned_to(base)
    s = _stats(base.values, cand_aligned)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    lines = [
        f"diff_map_regression_test  ({stamp})",
        f"baseline : {base.label}  EPSG:{base.crs}  shape={base.values.shape}",
        f"candidate: {cand.label}  EPSG:{cand.crs}  shape={cand.values.shape}",
        f"reprojected candidate -> baseline grid: {reprojected} "
        f"(nearest; EPSG:{cand.crs} -> EPSG:{base.crs})" if reprojected
        else "same grid; direct comparison",
        "",
        f"cells defined in both     : {s['both_defined']:,}",
        f"baseline-only (edge loss) : {s['baseline_only']:,}",
        f"candidate-only            : {s['candidate_only']:,}",
        "",
        f"exact-zero difference     : {s['exact_zero_pct']:.2f} %",
        f"within ±1 step            : {s['within_1_pct']:.2f} %",
        f"mean / std diff           : {s['mean']:+.3f} / {s['std']:.3f}",
        f"p95(|diff|) / max(|diff|) : {s['p95_abs']:.2f} / {s['max_abs']:.2f}",
        "",
        "Expectation: interior ~exact (CRS lattice shift gives a ±1-cell fringe);",
        "edge coverage differs (baseline-only) where the candidate bbox is smaller.",
    ]
    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)

    # ---- Figure: baseline | candidate-aligned | diff | hist ----
    diff = s["diff"]
    vlim = max(1.0, float(np.nanpercentile(np.abs(diff[s["both"]]), 99))) if s["both_defined"] else 1.0
    fig, ax = plt.subplots(2, 2, figsize=(13, 11))
    for a, arr, title in [
        (ax[0, 0], base.values, f"baseline (EPSG:{base.crs})"),
        (ax[0, 1], cand_aligned, f"candidate -> EPSG:{base.crs} grid"),
    ]:
        im = a.imshow(arr, cmap="viridis"); a.set_title(title, fontsize=10)
        fig.colorbar(im, ax=a, fraction=0.046, pad=0.04)
    imd = ax[1, 0].imshow(diff, cmap="RdBu_r", vmin=-vlim, vmax=vlim)
    ax[1, 0].set_title("candidate − baseline", fontsize=10)
    fig.colorbar(imd, ax=ax[1, 0], fraction=0.046, pad=0.04, extend="both")
    if s["both_defined"]:
        ax[1, 1].hist(diff[s["both"]], bins=61, color="#4c72b0")
        ax[1, 1].set_yscale("log")
    ax[1, 1].set_title("difference distribution (both-defined cells)", fontsize=10)
    ax[1, 1].set_xlabel("candidate − baseline")
    fig.suptitle(f"Diff regression — {base.label}\nvs {cand.label}", fontsize=11)
    fig.tight_layout()
    png = OUTPUT_DIR / f"{stamp}_diff.png"
    fig.savefig(png, dpi=150)
    print(f"\nSaved {png}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("baseline", type=Path, help="Reference product .npz")
    p.add_argument("candidate", type=Path, help="Product to test (reprojected onto baseline)")
    args = p.parse_args()
    for f in (args.baseline, args.candidate):
        if not f.exists():
            sys.exit(f"not found: {f}")
    run(args.baseline, args.candidate)


if __name__ == "__main__":
    main()