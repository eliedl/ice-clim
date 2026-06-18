"""Probe 008 — SGRDA / SGRDR Version Selection.

When several archive files exist for the same (region, date) — multiple clean
revisions ``pl_a``/``pl_b``/``pl_c`` and/or timestamped production-save suffixes
(``..._pl_b_YYYYMMDDHHMMSS.tar``) — ingestion must pick exactly one. This probe
reproduces the metrics that justified the selection rule already implemented in
``backend.ingestion.sources.ChartSource.discover``:

  1. Highest clean revision wins (c > b > a).
  2. A timestamped-suffix file is used only as a fallback when no clean file
     exists for that date.

Two diagnostics, per source (SGRDA GULF+WIS28, SGRDR EC):

  A. Suffix vs clean identity — for each (date, rev) with both a clean file and
     one or more timestamped-suffix files, compare feature counts. Suffix saves
     are expected to be redundant (counts match), so they carry no unique data.
  B. Clean revision comparison — for each date with multiple clean revisions,
     compare consecutive revisions (a->b, b->c) on feature count and bounding
     box. Higher revisions are expected to be corrections within an identical
     bbox (never spatial amendments), confirming c > b > a is a correction rank.

Also lists suffix-only dates (no clean file) — the fallback exceptions.

Reads charts exactly as the ingestion does (extract archive, read the ``*_pl_*``
polygon shapefile with geopandas). Feature count is ``len(gdf)``; bbox is
``gdf.total_bounds`` in the chart's native CRS — same-date files share a CRS, so
bounds compare directly without reprojection. Reuses the directory + filename
grammar from ``backend.ingestion.sources`` so the probe and the ingestion stay
on one definition of "what files exist".
"""

from __future__ import annotations

import re
import sys
import tarfile
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import geopandas as gpd

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ingestion.sources import SGRDA_SOURCE, SGRDR_SOURCE  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"
_REV_ORDER = {"a": 0, "b": 1, "c": 2}
_BBOX_NDIGITS = 3      # round total_bounds (metres) to mm before equality: absorbs sub-mm
                       # float/reprojection roundtrip noise, still catches any real (>= m)
                       # chart-extent amendment
_OUTLIER_DELTA = 50    # |feature-count delta| flagged for individual inspection

_metrics_cache: dict[str, tuple[int, tuple]] = {}


def _extract_pl_shp(path: Path, tmpdir: str) -> Path:
    """Extract a .tar or .zip archive and return its polygon (``*_pl_*``) shapefile."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmpdir)
    else:
        with tarfile.open(path) as tf:
            tf.extractall(tmpdir, filter="data")
    shps = sorted(Path(tmpdir).glob("*_pl_*.shp")) or sorted(Path(tmpdir).glob("*.shp"))
    if not shps:
        raise FileNotFoundError(f"No polygon shapefile in {path.name}")
    return shps[0]


def chart_metrics(path: Path) -> tuple[int, tuple]:
    """(feature_count, rounded bbox) for a chart archive; cached by path."""
    key = str(path)
    if key not in _metrics_cache:
        with tempfile.TemporaryDirectory() as tmp:
            shp = _extract_pl_shp(path, tmp)
            gdf = gpd.read_file(shp)
        bbox = tuple(round(float(v), _BBOX_NDIGITS) for v in gdf.total_bounds)
        _metrics_cache[key] = (len(gdf), bbox)
    return _metrics_cache[key]


def enumerate_candidates(source):
    """(region, date) -> {'clean': {rev: [Path]}, 'suffix': {rev: [Path]}}.

    Uses the source's own clean/suffix regexes and directories, so the probe
    enumerates the same universe of files the ingestion discovers — but keeps
    *all* candidates rather than selecting one.
    """
    cand = defaultdict(lambda: {"clean": defaultdict(list), "suffix": defaultdict(list)})
    for directory in source.directories:
        if not directory.exists():
            continue
        for glob_pat in source.file_globs:
            for path in directory.glob(glob_pat):
                for rx in source.clean_res:
                    m = rx.match(path.name)
                    if m:
                        region = source.region_label_map[m.group("region").upper()]
                        cand[(region, m.group("date"))]["clean"][m.group("rev").lower()].append(path)
                        break
                else:
                    for rx in source.suffix_res:
                        m = rx.match(path.name)
                        if m:
                            region = source.region_label_map[m.group("region").upper()]
                            cand[(region, m.group("date"))]["suffix"][m.group("rev").lower()].append(path)
                            break
    return cand


_TS_RE = re.compile(r"_\d{14}")             # production-save timestamp (YYYYMMDDHHMMSS)
_DATE_RE = re.compile(r"_\d{8}(T\d{4}Z)?")  # observation date + optional Thhmm Z


def normalize_pattern(name: str) -> str:
    """Collapse the obs-date and any production-save timestamp to placeholders —
    reproduces the sed normalization used in the original archive census. The
    14-digit timestamp is collapsed first so the remaining 8-digit run is the
    observation date (an optional ``Thhmm Z`` time is preserved, so 18:00Z vs a
    clock-drift 18:02Z surface as distinct patterns)."""
    name = _TS_RE.sub("_YYYYMMDDHHMMSS", name)
    name = _DATE_RE.sub(lambda m: "_DATE" + (m.group(1) or ""), name)
    return name


def pattern_census(source):
    """Distinct normalized filename patterns + counts, split into primary archives
    (selection candidates) vs timestamped production saves (excluded)."""
    counts: Counter = Counter()
    for directory in source.directories:
        if not directory.exists():
            continue
        for glob_pat in source.file_globs:
            for path in directory.glob(glob_pat):
                counts[normalize_pattern(path.name)] += 1
    primary = {p: c for p, c in counts.items() if "YYYYMMDDHHMMSS" not in p}
    saves = {p: c for p, c in counts.items() if "YYYYMMDDHHMMSS" in p}
    return primary, saves


def analyze(source, label) -> list[str]:
    cand = enumerate_candidates(source)
    n_clean = sum(len(p) for g in cand.values() for p in g["clean"].values())
    n_suffix = sum(len(p) for g in cand.values() for p in g["suffix"].values())

    # --- Probe A: suffix vs clean identity (same date + rev) ---
    a_tested = a_match = a_differ = a_errors = 0
    a_mismatches: list[tuple] = []
    for (region, date), g in cand.items():
        for rev, clean_paths in g["clean"].items():
            sfx_paths = g["suffix"].get(rev, [])
            if not sfx_paths:
                continue
            try:
                clean_n, _ = chart_metrics(clean_paths[0])
                for sp in sfx_paths:
                    sfx_n, _ = chart_metrics(sp)
                    a_tested += 1
                    if clean_n == sfx_n:
                        a_match += 1
                    else:
                        a_differ += 1
                        a_mismatches.append((region, date, rev, clean_n, sfx_n, sp.name))
            except Exception:
                a_errors += 1

    # --- Probe B: clean revision comparison (consecutive a->b, b->c) ---
    b_cmp = b_same_bbox = b_diff_bbox = b_same_count = b_diff_count = b_errors = 0
    deltas: Counter = Counter()
    b_outliers: list[tuple] = []
    b_diffbbox: list[tuple] = []
    for (region, date), g in cand.items():
        revs = sorted(g["clean"].keys(), key=lambda r: _REV_ORDER.get(r, 99))
        if len(revs) < 2:
            continue
        try:
            for lo, hi in zip(revs, revs[1:]):
                lo_n, lo_bb = chart_metrics(g["clean"][lo][0])
                hi_n, hi_bb = chart_metrics(g["clean"][hi][0])
                b_cmp += 1
                if lo_bb == hi_bb:
                    b_same_bbox += 1
                else:
                    b_diff_bbox += 1
                    b_diffbbox.append((region, date, lo, hi, lo_bb, hi_bb))
                d = hi_n - lo_n
                (deltas).update([d])
                if d == 0:
                    b_same_count += 1
                else:
                    b_diff_count += 1
                if abs(d) >= _OUTLIER_DELTA:
                    b_outliers.append((region, date, lo, hi, lo_n, hi_n, d))
        except Exception:
            b_errors += 1

    suffix_only = sorted(
        (region, date, sorted(g["suffix"].keys()))
        for (region, date), g in cand.items()
        if g["suffix"] and not g["clean"]
    )

    primary, saves = pattern_census(source)
    lines = [
        f"--- {label} ---",
        "",
        "  Filename pattern census — Primary archives (no _YYYYMMDDHHMMSS — selection candidates):",
        *[f"      {c:>6,}  {p}" for p, c in sorted(primary.items(), key=lambda x: -x[1])],
        "  Filename pattern census — Production saves (_YYYYMMDDHHMMSS suffix — excluded):",
        *[f"      {c:>6,}  {p}" for p, c in sorted(saves.items(), key=lambda x: -x[1])],
        "",
        f"  (region,date) groups: {len(cand):,}   clean files: {n_clean:,}   suffix files: {n_suffix:,}",
        "",
        "  Probe A — suffix vs clean identity (same date+rev, feature count):",
        f"    pairs_tested={a_tested:,}  match={a_match:,}  differ={a_differ:,}  read_errors={a_errors}",
    ]
    for region, date, rev, cn, sn, name in a_mismatches[:50]:
        lines.append(f"      DIFFER {region} {date} pl_{rev}: clean={cn} suffix={sn} ({name})")
    lines += [
        "",
        "  Probe B — clean revision comparison (consecutive a->b, b->c):",
        f"    comparisons={b_cmp:,}  same_bbox={b_same_bbox:,}  diff_bbox={b_diff_bbox:,}"
        f"  same_count={b_same_count:,}  diff_count={b_diff_count:,}  read_errors={b_errors}",
        "    feature-count delta (higher - lower) histogram:",
    ]
    for d in sorted(deltas):
        lines.append(f"      {d:+d}: {deltas[d]:,}")
    if b_outliers:
        lines.append(f"    outliers (|delta| >= {_OUTLIER_DELTA}):")
        for region, date, lo, hi, ln, hn, d in b_outliers:
            lines.append(f"      {region} {date} pl_{lo}->pl_{hi}: {ln} -> {hn} ({d:+d})")
    if b_diffbbox:
        lines.append("    DIFF-BBOX cases (expected none — would refute the correction-only rule):")
        for region, date, lo, hi, lbb, hbb in b_diffbbox:
            lines.append(f"      {region} {date} pl_{lo}->pl_{hi}: {lbb} -> {hbb}")
    lines += [
        "",
        f"  Suffix-only dates (no clean file — fallback exceptions): {len(suffix_only)}",
    ]
    for region, date, revs in suffix_only:
        lines.append(f"      {region} {date}: suffix revs {revs}")
    lines.append("")
    return lines


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"

    header = [
        "=== Probe 008 — SGRDA / SGRDREC Version Selection ===",
        f"Generated: {stamp}",
        "",
        "Validates the ingestion file-selection rule: highest clean revision c>b>a;",
        "timestamped-suffix fallback only when no clean file exists for a date.",
        "",
    ]
    body: list[str] = []
    for source, label in [(SGRDA_SOURCE, "SGRDA (GULF + WIS28)"),
                          (SGRDR_SOURCE, "SGRDR (EC)")]:
        body += analyze(source, label)

    report = "\n".join(header + body)
    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()