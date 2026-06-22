"""Probe 010 — CIS vs UQAR Freeze-Up Climatology Difference (Sept-Îles, 1991-2020).

Rasterizes the CIS 1991-2020 EC freeze-up normals (freeze.shp, weekly HD
classes) onto the climatology grid and differences them against our own
freeze-up climatology (FreezeUpDateMetric, sgrdr, winters 1991-2020) computed
through the production pipeline. Both rasters share the Sep-1-anchored
day-of-season ordinal axis (services.temporal.SEASON_ORIGIN).

Outputs per-cell signed difference (ours - CIS, days; positive = ours later),
maps, histogram, and agreement statistics keyed to the CIS weekly
quantization (half-week / one-week bands).

Our raster is cached as output/ours_values.npy after the first run;
pass --recompute to rebuild it from the DB.

--attribution mode (requires a cached raster): re-runnable record of the
cell-level diagnostics that attributed the two discrepancy populations:
  1. census + connected components of the non-zero difference cells;
  2. median-convention probe at sampled cells — per-year point-truth CT at
     the bracketing HDs, interpolated vs upper-middle median (identified the
     even-n median convention, DEC-035);
  3. burned-raster vs point-truth per year at the largest components'
     centre cells — flags years whose chart polygon is missing from the burn;
  4. inspection of each missing polygon: geometry type/validity, solo-burn
     result, and whether the *production* fetch filter
     (pipeline.fetch_domain_wkt) intersects it (identified the grid-edge
     under-fetch: the 2000-01-22 polygon lies inside the UTM grid envelope
     but outside the square fetch domain).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from shapely import wkt as swkt
from sqlalchemy import text

from climatology.services.temporal import SEASON_ORIGIN, day_of_season
from climatology.processing.metrics import FreezeUpDateMetric
from climatology.processing.pipeline import (
    GRID_CRS,
    build_grid,
    build_land_mask,
    burn,
    burn_values,
    fetch_domain_wkt,
    get_engine,
    load_polygons,
    region_paths,
)
from climatology.processing.sources import CHART_TABLES, LAND_MASK_PATH
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION

load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"
OURS_CACHE = OUTPUT_DIR / "ours_values.npy"

EC_FREEZE = Path("/home/eliedl/data/1991-2020_climatology_shapefiles/EC/freezeup/freeze.shp")

REGION = "sept-iles"
SOURCE = CHART_TABLES["sgrdr"]
CLIM_START, CLIM_END = "1990-09-01", "2020-09-01"   # winters 1991-2020 (half-open T1 window)
PERIOD_SLUG = "1991-2020"


def compute_ours(transform, h, w, *, recompute: bool,
                 median: str = "high") -> np.ndarray:
    """Our freeze-up raster through the production pipeline (cached).

    ``median`` selects the cross-year median convention of the CT cube:
    'high' = production (`_nanmedian_high`, DEC-035); 'interp' = the
    pre-DEC-035 interpolated `np.nanmedian`, kept re-runnable here via a
    probe-local override so the nanmedian-vs-CIS evidence can always be
    regenerated. The override never touches production code on disk.
    """
    cache = (OURS_CACHE if median == "high"
             else OUTPUT_DIR / "ours_values_interp_median.npy")
    if cache.exists() and not recompute:
        print(f"Using cached UQAR raster: {cache} (pass --recompute to rebuild)")
        return np.load(cache)
    if median == "interp":
        import climatology.processing.event_detection as ed
        assert hasattr(ed, "_nanmedian_high"), \
            "monkeypatch seam gone: event_detection._nanmedian_high was renamed"
        ed._nanmedian_high = lambda a: np.nanmedian(a, axis=0)
    metric = FreezeUpDateMetric()
    bbox_path, _, _ = region_paths(REGION, metric.slug,
                                   period_slug=PERIOD_SLUG, source_slug=SOURCE.slug)
    land_mask = build_land_mask(LAND_MASK_PATH, transform, h, w)
    df = load_polygons(metric, bbox_path, table=SOURCE.table,
                       climatology_start_date=CLIM_START, climatology_end_date=CLIM_END)
    if df.empty:
        sys.exit("ERROR: no rows returned — check DB / season range.")
    values = metric.compute_climatology(
        df, transform=transform, height=h, width=w,
        burn=burn, burn_values=burn_values, land_mask=land_mask,
    )
    np.save(cache, values)
    print(f"Cached UQAR raster: {cache}")
    return values


def rasterize_cis(transform, h, w) -> np.ndarray:
    """CIS freeze.shp weekly classes -> day-of-season ordinals on our grid.

    'freeze' holds MMDD HD labels ('1204'...'0312') plus '0' (the climate-
    normals landmask, DEC-034); land polygons are excluded so land stays NaN.
    """
    cis = gpd.read_file(EC_FREEZE).to_crs(GRID_CRS)
    ice = cis[cis["freeze"] != "0"].copy()
    ice["ordinal"] = ice["freeze"].map(lambda s: day_of_season(f"{s[:2]}-{s[2:]}"))
    return burn_values(list(zip(ice.geometry, ice["ordinal"])), transform, h, w)


def fmt_day(d: float) -> str:
    from datetime import timedelta
    return (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")


def stats_report(ours, cis, diff) -> list[str]:
    both = np.isfinite(ours) & np.isfinite(cis)
    ours_only = np.isfinite(ours) & ~np.isfinite(cis)
    cis_only = ~np.isfinite(ours) & np.isfinite(cis)
    d = diff[both]
    lines = [
        f"Cells with both defined : {both.sum():,}",
        f"Cells UQAR-only         : {ours_only.sum():,}",
        f"Cells CIS-only          : {cis_only.sum():,}",
        "",
        "Signed difference (UQAR - CIS, days; positive = ours later):",
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
        f"  UQAR : {np.nanmin(ours):.0f}-{np.nanmax(ours):.0f} "
        f"({fmt_day(np.nanmin(ours))} - {fmt_day(np.nanmax(ours))})",
        f"  CIS  : {np.nanmin(cis):.0f}-{np.nanmax(cis):.0f} "
        f"({fmt_day(np.nanmin(cis))} - {fmt_day(np.nanmax(cis))})",
    ]
    return lines


def plot(ours, cis, diff, bounds, stamp: str) -> Path:
    xmin, ymin, xmax, ymax = bounds
    extent = [xmin, xmax, ymin, ymax]
    both = np.isfinite(ours) & np.isfinite(cis)

    vmin = np.nanmin([np.nanmin(ours), np.nanmin(cis)])
    vmax = np.nanmax([np.nanmax(ours), np.nanmax(cis)])
    dmax = np.nanpercentile(np.abs(diff[both]), 99) if both.any() else 1.0

    fig, axes = plt.subplots(2, 2, figsize=(16, 13))
    for ax, arr, title, cmap, norm_kw in [
        (axes[0, 0], ours, f"UQAR freeze-up (sgrdr, {PERIOD_SLUG})", "viridis",
         dict(vmin=vmin, vmax=vmax)),
        (axes[0, 1], cis, "CIS freeze-up normals (freeze.shp)", "viridis",
         dict(vmin=vmin, vmax=vmax)),
        (axes[1, 0], diff, "UQAR - CIS (days; red = ours later)", "RdBu_r",
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
    ax.set_xlabel("UQAR - CIS (days); dashes = ±1 CIS week")
    ax.set_ylabel("cells")
    ax.set_title("Difference distribution")

    fig.suptitle(
        f"Probe 010 — CIS vs UQAR freeze-up climatology, {REGION}, "
        f"winters {PERIOD_SLUG} (UTM19N)", fontsize=13,
    )
    png = OUTPUT_DIR / f"{stamp}_difference.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    return png


# ── Attribution mode — re-runnable record of the cell-level diagnostics ─────

N_SAMPLE_CELLS = 8       # median-convention probe sample size
N_TOP_COMPONENTS = 3     # components probed for missing burn years
MIN_COMPONENT_CELLS = 100


def cell_centre_lonlat(r: int, c: int, bounds, w: int):
    xmin, ymin, xmax, ymax = bounds
    res = (xmax - xmin) / w
    px, py = xmin + (c + 0.5) * res, ymax - (r + 0.5) * res
    pt = gpd.GeoSeries.from_xy([px], [py], crs=GRID_CRS).to_crs(4326).iloc[0]
    return (px, py), pt


def point_ct_series(eng, pt_ll) -> pd.DataFrame:
    """Per-chart CT at a point over the climatology period (point-truth:
    independent of rasterization and of the production fetch filter)."""
    with eng.connect() as conn:
        s = pd.read_sql(text("""SELECT "T1"::date d, "CT" ct FROM sgrdr
            WHERE "POLY_TYPE" IN ('I','W')
            AND ST_Intersects(geometry, ST_GeomFromText(:p, 4326))
            AND "T1" BETWEEN :smin AND :smax"""),
            conn, params={"p": pt_ll.wkt, "smin": CLIM_START, "smax": "2020-08-31"})
    s["md"] = pd.to_datetime(s.d).dt.strftime("%m-%d")
    s["yr"] = pd.to_datetime(s.d).dt.year
    s["frac"] = s.ct.map(CONCENTRATION_FRACTION)
    return s


def median_convention_probe(eng, cells, ours, cis, bounds, w, lines) -> None:
    """Point-truth medians (interpolated vs upper-middle) at the bracketing HDs.

    A cell where med_interp < ct_threshold <= med_high at the CIS crossing HD
    is explained by the even-n median convention (DEC-035)."""
    lines.append("── Median-convention probe (point-truth CT series) ──")
    for r, c in cells:
        _, pt_ll = cell_centre_lonlat(r, c, bounds, w)
        s = point_ct_series(eng, pt_ll)
        cis_md, ours_md = fmt_md(cis[r, c]), fmt_md(ours[r, c])
        parts = [f"cell({r},{c}) CIS={cis_md} ours={ours_md}:"]
        for md in (cis_md, ours_md):
            v = np.sort(s.loc[s.md == md, "frac"].dropna().values)
            n = len(v)
            mi = np.median(v) if n else np.nan
            mh = v[n // 2] if n else np.nan
            parts.append(f"HD {md}: n={n:2d} med_interp={mi:.2f} med_high={mh:.2f}")
        lines.append("  " + " | ".join(parts))
    lines.append("")


def burn_vs_truth(eng, r, c, md, transform, h, w, bounds, bbox_wkt, lines) -> list[int]:
    """Per-year comparison of the burned raster vs point-truth at one cell,
    at the CIS crossing HD ``md`` ("MM-DD").

    Re-burns each year's chart through the production fetch filter and flags
    years where the cell value diverges from the point-in-polygon truth
    (a missing/mis-burned chart polygon)."""
    _, pt_ll = cell_centre_lonlat(r, c, bounds, w)
    truth = point_ct_series(eng, pt_ll)
    mismatch_years = []
    sub = truth[truth.md == md].set_index("yr")["frac"].sort_index()
    lines.append(f"── Burned vs point-truth, cell ({r},{c}), HD {md} ──")
    with eng.connect() as conn:
        for yr, t in sub.items():
            df = pd.read_sql(text(f"""SELECT ST_AsText(ST_Transform(geometry,{GRID_CRS})) gw, "CT" ct
                FROM sgrdr WHERE "POLY_TYPE" IN ('I','W') AND "T1"::date = :d
                AND ST_Intersects(geometry, ST_GeomFromText(:bb, 4326))"""),
                conn, params={"d": f"{yr}-{md}", "bb": bbox_wkt})
            df["frac"] = df.ct.map(CONCENTRATION_FRACTION)
            df = df.dropna(subset=["frac"])
            arr = burn_values(list(zip(df.gw.map(swkt.loads), df.frac)),
                              transform, h, w)
            burned = arr[r, c]
            ok = np.isfinite(burned) and abs(burned - t) < 1e-6
            if not ok:
                mismatch_years.append(yr)
                lines.append(f"  {yr}: truth={t:.2f}  burned={burned:.2f}  <-- MISMATCH")
    if not mismatch_years:
        lines.append("  (all years match point-truth)")
    lines.append("")
    return mismatch_years


def inspect_missing_polygon(eng, yr, md, r, c, transform, h, w, bounds,
                            bbox_wkt, lines) -> None:
    """Why is a chart polygon absent from the burn? Geometry diagnostics +
    the production fetch-filter test on the polygon containing the cell."""
    _, pt_ll = cell_centre_lonlat(r, c, bounds, w)
    with eng.connect() as conn:
        df = pd.read_sql(text("""SELECT "CT" ct, "POLY_TYPE",
                GeometryType(geometry) gtype, ST_IsValid(geometry) valid,
                ST_Intersects(geometry, ST_GeomFromText(:bb, 4326)) hits_fetch_domain,
                ST_YMax(geometry) ymax_ll,
                ST_AsText(ST_Transform(geometry, %d)) gw
            FROM sgrdr WHERE "T1"::date = :d
            AND ST_Intersects(geometry, ST_GeomFromText(:p, 4326))""" % GRID_CRS),
            conn, params={"d": f"{yr}-{md}", "bb": bbox_wkt, "p": pt_ll.wkt})
    lines.append(f"── Missing-polygon inspection, {yr}-{md}, cell ({r},{c}) ──")
    if df.empty:
        lines.append("  (no polygon contains the cell centre — coverage gap)")
        lines.append("")
        return
    for _, row in df.iterrows():
        g = swkt.loads(row.gw)
        solo = burn_values([(g, 1.0)], transform, h, w)
        lines.append(
            f"  CT={row.ct} type={row.gtype} valid={row.valid} "
            f"ymax_ll={row.ymax_ll:.5f}"
        )
        lines.append(
            f"  solo-burn: {int(np.isfinite(solo).sum()):,} cells, "
            f"cell value={'burned' if np.isfinite(solo[r, c]) else 'NOT burned'}"
        )
        lines.append(
            f"  production fetch filter intersects polygon: {row.hits_fetch_domain}"
            + ("  <-- UNDER-FETCH: in-grid polygon excluded by the filter"
               if not row.hits_fetch_domain else "")
        )
    lines.append("")


def fmt_md(ordinal: float) -> str:
    from datetime import timedelta
    return (SEASON_ORIGIN + timedelta(days=int(ordinal))).strftime("%m-%d")


def attribution(stamp: str, raster_path: Path) -> None:
    from scipy import ndimage

    if not raster_path.exists():
        sys.exit(f"ERROR: --attribution needs a cached raster ({raster_path} "
                 "not found; run the probe first).")
    bbox_path, _, _ = region_paths(REGION, FreezeUpDateMetric.slug,
                                   period_slug=PERIOD_SLUG, source_slug=SOURCE.slug)
    transform, h, w, bounds = build_grid(bbox_path)
    ours = np.load(raster_path)
    cis = rasterize_cis(transform, h, w)
    diff = ours - cis
    eng = get_engine()
    bbox_wkt = fetch_domain_wkt(bbox_path)

    lines = ["=== Probe 010 — attribution diagnostics ===",
             f"Generated: {stamp}",
             f"UQAR raster: {raster_path}",
             "(diagnoses whichever pipeline state produced that raster; the",
             " fetch-filter test reflects the *current* production filter)", ""]

    # 1. census + connected components
    nz = np.isfinite(diff) & (diff != 0)
    vals, counts = np.unique(diff[nz], return_counts=True)
    lines.append(f"Non-zero difference cells: {nz.sum():,}")
    lines.append("  values: " + ", ".join(
        f"{v:+.0f}d x {n:,}" for v, n in zip(vals, counts)))
    lab, ncomp = ndimage.label(nz)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    order = np.argsort(sizes)[::-1]
    lines.append(f"  {ncomp:,} connected components; sizes (top 10): "
                 f"{sizes[order[:10]].tolist()}")
    top = [int(li) for li in order[:N_TOP_COMPONENTS]
           if sizes[li] >= MIN_COMPONENT_CELLS]
    centres = []
    for li in top:
        ys, xs = np.where(lab == li)
        r, c = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
        centres.append((r, c))
        lines.append(f"  component size={sizes[li]:,}  diff={diff[r, c]:+.0f}d  "
                     f"centre=({r},{c})  ours={fmt_md(ours[r, c])} "
                     f"cis={fmt_md(cis[r, c])}")
    lines.append("")

    # 2. median-convention probe at sampled non-zero cells
    rng = np.random.default_rng(42)
    ys, xs = np.where(nz)
    idx = rng.choice(len(ys), size=min(N_SAMPLE_CELLS, len(ys)), replace=False)
    median_convention_probe(eng, [(int(ys[k]), int(xs[k])) for k in idx],
                            ours, cis, bounds, w, lines)

    # 3 + 4. burned-vs-truth + missing-polygon inspection at component centres
    for r, c in centres:
        md = fmt_md(cis[r, c])
        missing = burn_vs_truth(eng, r, c, md, transform, h, w, bounds,
                                bbox_wkt, lines)
        for yr in missing:
            inspect_missing_polygon(eng, yr, md, r, c,
                                    transform, h, w, bounds, bbox_wkt, lines)

    out = OUTPUT_DIR / f"{stamp}_attribution.txt"
    report = "\n".join(lines)
    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true",
                    help="Rebuild the UQAR raster from the DB instead of the cache.")
    ap.add_argument("--attribution", action="store_true",
                    help="Run the cell-level attribution diagnostics on a "
                         "cached raster instead of the difference report.")
    ap.add_argument("--raster", type=Path, default=OURS_CACHE,
                    help="Cached raster to diagnose in --attribution mode "
                         "(default: the current cache; point at a preserved "
                         ".npy to re-derive a historical attribution, e.g. "
                         "ours_values_interp_median.npy for the DEC-035 "
                         "nanmedian evidence).")
    ap.add_argument("--median", choices=("high", "interp"), default="high",
                    help="Cross-year median convention for the UQAR raster: "
                         "'high' = production (DEC-035); 'interp' = the "
                         "pre-DEC-035 np.nanmedian, regenerating the "
                         "nanmedian-vs-CIS evidence (cached separately as "
                         "ours_values_interp_median.npy).")
    args = ap.parse_args()

    if args.attribution:
        OUTPUT_DIR.mkdir(exist_ok=True)
        attribution(datetime.now().strftime("%Y-%m-%d_%H%M%S"), args.raster)
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    bbox_path, _, _ = region_paths(REGION, FreezeUpDateMetric.slug,
                                   period_slug=PERIOD_SLUG, source_slug=SOURCE.slug)
    transform, h, w, bounds = build_grid(bbox_path)

    ours = compute_ours(transform, h, w, recompute=args.recompute,
                        median=args.median)
    cis = rasterize_cis(transform, h, w)
    diff = ours - cis

    lines = ["=== Probe 010 — CIS vs UQAR freeze-up difference ===",
             f"Generated: {stamp}",
             f"Region: {REGION} | Source: {SOURCE.slug} | Winters: {PERIOD_SLUG}",
             f"Median convention: {args.median}",
             f"Grid: {w} x {h} @ EPSG:{GRID_CRS}", ""]
    lines += stats_report(ours, cis, diff)

    png = plot(ours, cis, diff, bounds, stamp)

    out = OUTPUT_DIR / f"{stamp}.txt"
    report = "\n".join(lines)
    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}\nSaved: {png}")


if __name__ == "__main__":
    main()
