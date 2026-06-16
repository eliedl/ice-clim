"""Probe 014 — SGRDA on-disk CRS by era (DEC-038).

Characterizes the **native CRS of SGRDA chart shapefiles across the archive**, to
validate the ingestion CRS branch and the DEC-038 assumption that CRS-less
charts are geographic degrees safely labelled EPSG:4326.

Why this exists: a quick look while validating DEC-038 found the SGRDA *GULF*
era is **not** CRS-homogeneous — the 2006 chart is `.prj`-less with geographic
(lon/lat) coordinates, but 2015 and 2022 GULF charts carry a projected
`WGS_1984_Lambert_Conformal_Conic` `.prj` (central meridian −100, SP 49/77,
metre coordinates). The project's documented model ("SGRDAGULF = old, no CRS →
4326; WIS28 = polar stereographic") is therefore incomplete. This probe maps the
actual CRS regime per (era, year) so DEC-038 and CLAUDE.md rest on data, not an
assumption.

The ingestion branch under test (`backend/ingestion/pipeline.py:39-42`):
    crs is None              -> set_crs(4326)        # must be geographic degrees
    crs.to_epsg() != 4326    -> to_crs(4326)         # any other CRS reprojected
    else                     -> keep                 # already 4326
For each sampled chart the probe reports which branch applies and whether the
coordinate magnitudes are consistent with the declared (or assumed) CRS.

Sampling: one chart per (era, year) by default — enough to draw the CRS-regime
timeline cheaply; `--all` reads every chart (slow). No DB access; reads the
archive (set ARCHIVE_ROOT, default /home/eliedl/data).

Run:
    .venv/bin/python -m backend.probes.014_sgrda_crs_by_era.probe [--all]
"""

from __future__ import annotations

import os
import re
import sys
import tarfile
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import geopandas as gpd

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/home/eliedl/data"))
SGRDA_ROOT = ARCHIVE_ROOT / "CIS" / "SGRDA"
OUTPUT_DIR = Path(__file__).parent / "output"

_DATE_RE = re.compile(r"_(\d{8})(?:T\d{4}Z)?_")


def _classify(crs, bounds) -> tuple[str, str]:
    """(ingestion branch, CRS-consistency verdict) for one chart."""
    span = max(abs(v) for v in bounds)
    looks_degrees = span <= 360.0
    if crs is None:
        branch = "set_crs(4326)"
        verdict = ("OK: CRS-less + geographic degrees -> 4326 valid"
                   if looks_degrees else
                   "!! CRS-less but coords are NOT degrees (span %.0f) — 4326 WRONG"
                   % span)
        return branch, verdict
    epsg = crs.to_epsg()
    if epsg == 4326:
        return "keep (already 4326)", "OK: declared 4326"
    kind = "geographic" if crs.is_geographic else "projected"
    name = crs.name or "?"
    consistent = (kind == "geographic") == looks_degrees
    verdict = (f"OK: {kind} {name} (epsg={epsg}) -> to_crs(4326)"
               if consistent else
               f"!! {kind} {name} but coord span {span:.0f} mismatches kind")
    return "to_crs(4326)", verdict


def _read_chart_crs(tar_path: Path):
    """(crs, bounds) for the .shp inside ``tar_path`` (extracted to a tmp dir)."""
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(tar_path) as tf:
            tf.extractall(td)
        shp = next(Path(td).rglob("*.shp"), None)
        if shp is None:
            raise FileNotFoundError("no .shp in tar")
        gdf = gpd.read_file(shp)
        return gdf.crs, tuple(gdf.total_bounds)


def _sample(all_charts: bool) -> dict[str, list[Path]]:
    """{era: [tar paths]} — one per year unless ``all_charts``."""
    out: dict[str, list[Path]] = {}
    for era_dir in sorted(p for p in SGRDA_ROOT.iterdir() if p.is_dir()):
        tars = sorted(era_dir.glob("*.tar"))
        if not tars:
            continue
        if all_charts:
            out[era_dir.name] = tars
            continue
        by_year: dict[str, Path] = {}
        for t in tars:
            m = _DATE_RE.search(t.name)
            if m:
                by_year.setdefault(m.group(1)[:4], t)
        out[era_dir.name] = [by_year[y] for y in sorted(by_year)]
    return out


def run(all_charts: bool = False) -> None:
    if not SGRDA_ROOT.is_dir():
        sys.exit(f"SGRDA archive not found: {SGRDA_ROOT} (set ARCHIVE_ROOT)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    lines = [f"Probe 014 — SGRDA on-disk CRS by era  ({stamp})",
             f"archive: {SGRDA_ROOT}   sampling: {'ALL charts' if all_charts else 'one per (era, year)'}",
             ""]
    regime_summary: dict[str, set[str]] = defaultdict(set)

    for era, tars in _sample(all_charts).items():
        lines.append(f"=== {era} ===")
        for t in tars:
            m = _DATE_RE.search(t.name)
            date = m.group(1) if m else "????????"
            try:
                crs, bounds = _read_chart_crs(t)
            except Exception as exc:
                lines.append(f"  {date}: ERROR {type(exc).__name__}: {exc}")
                continue
            branch, verdict = _classify(crs, bounds)
            name = "None" if crs is None else (crs.name or f"epsg={crs.to_epsg()}")
            regime_summary[era].add(name)
            lines.append(
                f"  {date}: crs={name:42.42}  bounds≈"
                f"({bounds[0]:.1f},{bounds[1]:.1f},{bounds[2]:.1f},{bounds[3]:.1f})"
            )
            lines.append(f"           branch={branch:18} {verdict}")
        lines.append("")

    lines.append("=== CRS regimes per era ===")
    for era, names in regime_summary.items():
        lines.append(f"  {era}: {sorted(names)}")

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    run(all_charts="--all" in sys.argv[1:])