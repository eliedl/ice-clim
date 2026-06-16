"""Probe 013 — NAD83 / Québec Lambert (32198) scale-factor map (DEC-040).

Quantifies the projection distortion of EPSG:32198 across Québec — the
evidence behind adopting it as the single end-product CRS — and contrasts it
with the zone-dependent UTM 26919.

Why it matters: `grid_crs` is both the compute CRS and the display CRS, so its
scale factor k sets the gap between nominal grid metres (`res_m`) and true
ground metres. For a Lambert Conformal Conic, k depends almost entirely on
*latitude* (zero on the two standard parallels 46°N/60°N, <1 between, >1
outside) — horizontal bands. For UTM it depends on *longitude* (1 on the
central meridian, growing off it) — vertical bands, which is why a single UTM
zone cannot serve all of Québec.

Resolution-floor framing (DEC-040): CIS SIGRID-3 polygon resolution dominates;
the projection ground error (k−1)·res is the lower bound only in the limit of
infinite source resolution. This probe reports that ground error at 25 / 100 /
1000 m so the negligible magnitude is on record.

Outputs, per region (legacy squares + adaptive), max/mean |k−1| over the region
and the implied ground error at each resolution; a 2-panel |k−1| map
(32198 horizontal bands vs 26919 vertical bands); and the 26919-at-Minganie
contrast.

No DB access; uses pyproj scale factors + the production region builder.

Run:
    .venv/bin/python -m backend.probes.013_qc_lambert_scale_factor.probe
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyproj import Proj
from shapely.geometry import box

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from climatology.processing.pipeline import LAND_DISPLAY_PATH  # noqa: E402
from climatology.processing.regions import REGION_SLUGS, resolve_region  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

QC_LON = (-80.0, -57.0)
QC_LAT = (44.0, 63.0)
RES_M = (25.0, 100.0, 1000.0)


def scale_field(epsg: int, lon, lat):
    """Point scale factor k on a lon/lat mesh for `epsg` (conformal: h == k)."""
    proj = Proj(f"EPSG:{epsg}")
    return np.asarray(proj.get_factors(lon, lat).meridional_scale)


def region_stats(slug: str):
    """(max|k-1|, mean|k-1|) of EPSG:32198 sampled over the region polygon in 4326."""
    spec = resolve_region(slug)
    geom_4326 = (
        gpd.GeoSeries([t.bounds_geom for t in spec.tiers], crs=spec.grid_crs)
        .to_crs(epsg=4326)
        .union_all()
    )
    # Sample on a fine lon/lat grid clipped to the region's bbox.
    minx, miny, maxx, maxy = geom_4326.bounds
    lons = np.linspace(minx, maxx, 60)
    lats = np.linspace(miny, maxy, 60)
    lo, la = np.meshgrid(lons, lats)
    k = scale_field(32198, lo, la)
    dev = np.abs(k - 1.0)
    return float(dev.max()), float(dev.mean()), spec.grid_crs


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    lons = np.linspace(*QC_LON, 240)
    lats = np.linspace(*QC_LAT, 240)
    lo, la = np.meshgrid(lons, lats)
    k_lam = scale_field(32198, lo, la)
    k_utm = scale_field(26919, lo, la)

    lines = [
        f"Probe 013 — EPSG:32198 scale-factor distortion  ({stamp})",
        f"QC sampling window: lon {QC_LON}, lat {QC_LAT}",
        "",
        "32198 (Québec Lambert) over QC window:"
        f"  max|k-1| = {np.abs(k_lam - 1).max() * 1e3:.3f} ppt"
        f"   mean = {np.abs(k_lam - 1).mean() * 1e3:.3f} ppt",
        "26919 (UTM 19N) over same window:"
        f"  max|k-1| = {np.abs(k_utm - 1).max() * 1e3:.3f} ppt"
        f"   (grows without bound off the 69°W meridian)",
        "",
        "Per-region 32198 distortion and implied ground error (|k-1|·res):",
        f"{'region':<22}{'grid_crs':>9}{'max|k-1|(ppt)':>15}"
        + "".join(f"{f'err@{int(r)}m':>12}" for r in RES_M),
    ]
    for slug in REGION_SLUGS:
        try:
            kmax, kmean, gcrs = region_stats(slug)
        except Exception as exc:  # missing bbox file / layer — skip, keep going
            lines.append(f"{slug:<22}  (skipped: {type(exc).__name__}: {exc})")
            continue
        errs = "".join(f"{kmax * r * 100:>11.2f}cm" for r in RES_M)
        lines.append(f"{slug:<22}{gcrs:>9}{kmax * 1e3:>15.3f}{errs}")

    # 26919-at-Minganie contrast (why UTM was rejected there, DEC-036).
    try:
        spec = resolve_region("minganie")
        g = (gpd.GeoSeries([t.bounds_geom for t in spec.tiers], crs=spec.grid_crs)
             .to_crs(epsg=4326).union_all())
        minx, miny, maxx, maxy = g.bounds
        lo2, la2 = np.meshgrid(np.linspace(minx, maxx, 60), np.linspace(miny, maxy, 60))
        k32 = np.abs(scale_field(32198, lo2, la2) - 1).max()
        k26 = np.abs(scale_field(26919, lo2, la2) - 1).max()
        smaller = "26919" if k26 < k32 else "32198"
        lines += [
            "",
            "Minganie contrast (max|k-1|, ppt):"
            f"  32198 = {k32 * 1e3:.3f}   26919 = {k26 * 1e3:.3f}"
            f"   (smaller POINT distortion here: {smaller})",
            "NOTE: at Minganie 26919's isotropic point scale is not larger than",
            "32198's — both are conformal and modest. The case for 32198 is NOT",
            "smaller point distortion but province-wide CONSISTENCY: Minganie is",
            "UTM-20N territory, so the proper UTM CRS there (26920) differs from",
            "the zone-19 regions (Gaspé/Sept-Îles) -> multi-zone seams. 32198 is",
            "one seamless frame for all of Québec (DEC-040).",
        ]
    except Exception as exc:
        lines.append(f"\nMinganie contrast skipped: {type(exc).__name__}: {exc}")

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)

    # OSM land (4326) for the gulf — overlay so distortion bands are read against
    # wet vs dry cells. File is gulf-clipped, so it covers only the maritime part
    # of the QC window; that is the region of interest anyway.
    try:
        land = gpd.read_file(LAND_DISPLAY_PATH).to_crs(epsg=4326)
        land = land.clip(box(QC_LON[0], QC_LAT[0], QC_LON[1], QC_LAT[1]))
    except Exception as exc:
        print(f"  (OSM coastline overlay skipped: {type(exc).__name__}: {exc})")
        land = None

    # ---- 2-panel |k-1| map: Lambert (horizontal bands) vs UTM (vertical bands) ----
    dev_lam = np.abs(k_lam - 1.0) * 1e3
    dev_utm = np.abs(k_utm - 1.0) * 1e3
    # Shared colour scale at the 98th percentile of the combined field -> more
    # mid-range contrast than the previous washed-out p99*4 ceiling.
    vmax = float(np.percentile(np.concatenate([dev_lam.ravel(), dev_utm.ravel()]), 98))

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    for ax, dev, title, parallels in [
        (axes[0], dev_lam, "EPSG:32198 — Québec Lambert  |k−1| (ppt)", (46.0, 60.0)),
        (axes[1], dev_utm, "EPSG:26919 — UTM 19N  |k−1| (ppt)", None),
    ]:
        pc = ax.pcolormesh(lons, lats, dev, shading="auto", cmap="viridis", vmax=vmax)
        fig.colorbar(pc, ax=ax, fraction=0.046, pad=0.04, extend="max",
                     label="|k−1| (parts/1000)")
        if land is not None and not land.empty:
            land.boundary.plot(ax=ax, color="w", linewidth=0.5, zorder=3)
        if parallels:
            for p in parallels:
                ax.axhline(p, color="#ff5555", ls="--", lw=0.8)
                ax.text(QC_LON[0] + 0.5, p + 0.2, f"{p:g}°N (k=1)", color="#ff5555",
                        fontsize=8)
        else:
            ax.axvline(-69.0, color="#ff5555", ls="--", lw=0.8)
            ax.text(-69.0 + 0.3, QC_LAT[0] + 0.5, "69°W (k₀)", color="#ff5555", fontsize=8)
        ax.set_xlim(*QC_LON)
        ax.set_ylim(*QC_LAT)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    fig.suptitle("DEC-040: Lambert (latitude-banded) vs UTM (longitude-banded) distortion",
                 fontsize=12)
    fig.tight_layout()
    png = OUTPUT_DIR / f"{stamp}_scale_factor.png"
    fig.savefig(png, dpi=150)
    print(f"\nSaved {png}")

    # ---- GSL-centred figure: signed error in cm per 100 m cell ----
    # cm per 100 m cell = (k-1) * 100 m * 100 cm/m = (k-1)*1e4 cm. Signed so
    # compression (k<1) and expansion (k>1) read as the two colour directions.
    if land is not None and not land.empty:
        gxmin, gymin, gxmax, gymax = land.total_bounds
    else:
        gxmin, gymin, gxmax, gymax = -70.5, 45.0, -56.0, 52.5
    pad = 0.5
    glon = np.linspace(gxmin - pad, gxmax + pad, 240)
    glat = np.linspace(gymin - pad, gymax + pad, 240)
    glo, gla = np.meshgrid(glon, glat)
    cm_lam = (scale_field(32198, glo, gla) - 1.0) * 1e4
    cm_utm = (scale_field(26919, glo, gla) - 1.0) * 1e4
    vlim = float(np.percentile(np.abs(np.concatenate([cm_lam.ravel(), cm_utm.ravel()])),
                               98))

    fig2, axes2 = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    for ax, cm, title, parallels in [
        (axes2[0], cm_lam, "EPSG:32198 — Québec Lambert", (46.0, 60.0)),
        (axes2[1], cm_utm, "EPSG:26919 — UTM 19N", None),
    ]:
        pc = ax.pcolormesh(glon, glat, cm, shading="auto", cmap="RdBu_r",
                           vmin=-vlim, vmax=vlim)
        fig2.colorbar(pc, ax=ax, fraction=0.046, pad=0.04, extend="both",
                      label="signed error (cm per 100 m cell)   − compression / + expansion")
        if land is not None and not land.empty:
            land.boundary.plot(ax=ax, color="k", linewidth=0.5, zorder=3)
        if parallels:
            for p in parallels:
                if glat[0] <= p <= glat[-1]:
                    ax.axhline(p, color="k", ls="--", lw=0.8)
                    ax.text(glon[0] + 0.2, p + 0.1, f"{p:g}°N (k=1)", fontsize=8)
        else:
            ax.axvline(-69.0, color="k", ls="--", lw=0.8)
            ax.text(-69.0 + 0.1, glat[0] + 0.2, "69°W (k₀)", fontsize=8)
        ax.set_xlim(glon[0], glon[-1])
        ax.set_ylim(glat[0], glat[-1])
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Longitude")
    axes2[0].set_ylabel("Latitude")
    fig2.suptitle("DEC-040: GSL distortion, signed cm per 100 m cell "
                  "(1 ppt = 10 cm / 100 m)", fontsize=12)
    fig2.tight_layout()
    png2 = OUTPUT_DIR / f"{stamp}_scale_factor_gsl_cm.png"
    fig2.savefig(png2, dpi=150)
    print(f"Saved {png2}")


if __name__ == "__main__":
    run()
