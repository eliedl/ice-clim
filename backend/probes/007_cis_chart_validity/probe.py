"""Probe 007 — CIS chart provenance/resolution metadata by era.

Answers the [cis-002] comparability question: do the CIS chart `.xml` sidecars
carry, consistently across decades, the two fields a climatology needs to judge
inter-era comparability — (1) the observation *source/sensor* that produced the
chart, and (2) an effective *spatial resolution*?

Data source: the raw archive `.xml` sidecars (FGDC CSDGM), which are NOT in the
PostGIS DB. The probe walks the archive (set ARCHIVE_ROOT, default
/home/eliedl/data), extracts each sampled chart's `.xml` from its tar/zip, and
censuses the lineage `<srcinfo>` blocks and the `<absres>` resolution field.

Key finding this probe formalizes (see README): the `<srcinfo>` list is a
program-history *catalogue* (identical boilerplate regardless of chart date, per
the `<procdesc>` text), NOT a per-chart sensor manifest. The only per-chart
signal is intersecting the chart date with each source's `<begdate>/<enddate>`
availability window ("active_at_date" below). The digitized-historical SGRDR
`CIS_EC_*` zips carry a *degenerate* single-source catalogue (RADARSAT only,
dated 1996+) — no usable provenance for the pre-satellite record.

Sampling (per user spec): SGRDA & SGRDI every 5 years (GSL lineage — SGRDA
GULF→WIS28, SGRDI GULF); SGRDR every decade (EC: historical zips + modern
tars). One representative — the earliest chart — per (bucket × packaging).

Run:
    .venv/bin/python backend/probes/007_cis_chart_validity/probe.py
Outputs to output/YYYY-MM-DD_HHMMSS{.txt,_field_presence.csv}.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/home/eliedl/data"))
CIS_ROOT = ARCHIVE_ROOT / "CIS"
OUTPUT_DIR = Path(__file__).parent / "output"

_DATE_RE = re.compile(r"_(\d{8})(?:T\d{4}Z)?_")


@dataclass
class ChartSeries:
    """One census series: where to look, and how coarsely to sample it."""

    name: str
    globs: list[Path]  # archive globs, scanned in order
    interval_years: int  # sampling bucket width


SERIES = [
    ChartSeries(
        "SGRDA (GSL daily: GULF)",
        [CIS_ROOT / "SGRDA" / "GULF" / "*.tar"],
        interval_years=5,
    ),
    ChartSeries(
        "SGRDA (GSL daily: WIS28)",
        [CIS_ROOT / "SGRDA" / "WIS28" / "*.tar"],
        interval_years=5,
    ),
    ChartSeries(
        "SGRDI (GSL satellite image analysis: GULF)",
        [CIS_ROOT / "SGRDI" / "GULF" / "*.tar"],
        interval_years=5,
    ),
    ChartSeries(
        "SGRDR (EC regional: historical zip + modern tar)",
        [CIS_ROOT / "SGRDR" / "EC" / "*.zip",
         CIS_ROOT / "SGRDR" / "EC" / "*.tar"],
        interval_years=10,
    ),
]


@dataclass
class Source:
    """One `<srcinfo>` lineage entry."""

    title: str
    typesrc: str
    begdate: str
    enddate: str

    def active_on(self, yyyymmdd: str) -> bool:
        """Does this source's availability window contain the chart date?"""
        if not (self.begdate.isdigit() and len(self.begdate) == 8):
            return False
        if yyyymmdd < self.begdate:
            return False
        end = self.enddate
        if end.isdigit() and len(end) == 8:
            return yyyymmdd <= end
        return True  # "still active" / open-ended


@dataclass
class ChartMeta:
    """Parsed provenance/resolution census for one chart's sidecar."""

    date: str
    packaging: str
    sources: list[Source] = field(default_factory=list)
    absres: str = "-"
    plandu: str = "-"
    procdesc: str = ""

    @property
    def n_sources(self) -> int:
        return len(self.sources)

    @property
    def quality(self) -> str:
        """Provenance catalogue quality tier."""
        if self.n_sources <= 1:
            return "degenerate"
        if self.n_sources >= 11:
            return "full"
        return "partial"

    def active_at_date(self) -> list[str]:
        return [s.title for s in self.sources if s.active_on(self.date)]


def _read_xml_bytes(archive: Path) -> bytes:
    """Extract the single `.xml` sidecar from a tar or zip archive."""
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            name = next(n for n in tf.getnames() if n.lower().endswith(".xml"))
            member = tf.extractfile(name)
            assert member is not None
            return member.read()
    with zipfile.ZipFile(archive) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        return zf.read(name)


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse(data: bytes, date: str, packaging: str) -> ChartMeta:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        root = ET.fromstring(data.decode("latin-1", "replace"))
    meta = ChartMeta(date=date, packaging=packaging)
    for si in root.findall(".//srcinfo"):
        meta.sources.append(Source(
            title=_text(si.find(".//title")),
            typesrc=_text(si.find("typesrc")),
            begdate=_text(si.find(".//begdate")),
            enddate=_text(si.find(".//enddate")),
        ))
    absres = root.find(".//absres")
    if absres is not None:
        meta.absres = _text(absres)
    plandu = root.find(".//plandu")
    if plandu is not None:
        meta.plandu = _text(plandu)
    proc = root.find(".//procdesc")
    if proc is not None:
        meta.procdesc = re.sub(r"\s+", " ", _text(proc))
    return meta


def _sample(series: ChartSeries) -> list[Path]:
    """Earliest archive per (interval bucket × packaging), across the globs.

    Bucketing by packaging as well as date guarantees a distinct-vintage
    boundary that falls *inside* a bucket (e.g. the SGRDR zip→tar switch, both
    in the 2020s decade) is still represented rather than masked by date sort.
    """
    dated: dict[str, tuple[str, Path]] = {}  # bucket:ext -> (date, path)
    for g in series.globs:
        for p in g.parent.glob(g.name):
            m = _DATE_RE.search(p.name)
            if not m:
                continue
            date = m.group(1)
            bucket = (int(date[:4]) // series.interval_years) * series.interval_years
            key = f"{bucket}:{p.suffix}"
            prev = dated.get(key)
            if prev is None or date < prev[0]:
                dated[key] = (date, p)
    return [path for _date, path in sorted(dated.values())]


def run() -> None:
    if not CIS_ROOT.is_dir():
        sys.exit(f"CIS archive not found: {CIS_ROOT} (set ARCHIVE_ROOT)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    lines = [
        f"Probe 007 — CIS chart provenance/resolution metadata by era  ({stamp})",
        f"archive: {CIS_ROOT}",
        "sampling: SGRDA every 5 yr (GSL lineage), SGRDR every decade (EC)",
        "",
        "'active_at_date' = sources whose <begdate>-<enddate> window contains the",
        "chart date (the ONLY per-chart provenance signal; the full <srcinfo> list",
        "is a program-history catalogue, identical regardless of chart date).",
        "",
    ]
    csv_rows: list[dict] = []

    for series in SERIES:
        samples = _sample(series)
        lines.append("=" * 78)
        lines.append(f"{series.name}   ({len(samples)} samples)")
        lines.append("=" * 78)
        for path in samples:
            date = _DATE_RE.search(path.name).group(1)
            packaging = path.suffix.lstrip(".")
            try:
                meta = _parse(_read_xml_bytes(path), date, packaging)
            except Exception as exc:  # noqa: BLE001 — probe: report and continue
                lines.append(f"  {date} [{packaging}]: ERROR "
                             f"{type(exc).__name__}: {exc}")
                continue
            active = meta.active_at_date()
            lines.append(
                f"  {date} [{packaging}]  n_srcinfo={meta.n_sources:<2} "
                f"quality={meta.quality:<10} absres={meta.absres} {meta.plandu}"
            )
            lines.append(f"      catalogue : "
                         f"{', '.join(s.title for s in meta.sources) or '(none)'}")
            lines.append(f"      active@date: {', '.join(active) or '(none)'}")
            csv_rows.append({
                "series": series.name,
                "sample_date": date,
                "packaging": packaging,
                "n_sources": meta.n_sources,
                "provenance_quality": meta.quality,
                "n_active_at_date": len(active),
                "active_at_date": "; ".join(active),
                "catalogue": "; ".join(s.title for s in meta.sources),
                "absres": meta.absres,
                "plandu": meta.plandu,
            })
        lines.append("")

    lines.append("=== NOTES ===")
    lines.append("- <srcinfo> is a program-history CATALOGUE, not a per-chart")
    lines.append("  sensor manifest (see <procdesc>: 'Over the years, data sources")
    lines.append("  have included...'). quality=degenerate means only 1 block")
    lines.append("  (RADARSAT, dated 1996+) — no usable provenance for that era.")
    lines.append("- <absres> is PLANAR COORDINATE precision (near-constant template")
    lines.append("  value), NOT observational/sensor ground resolution; it does not")
    lines.append("  map to CISADS No.1 Table 3.1. No observational-resolution field")
    lines.append("  exists — resolution is inferable only via the sensor-class name.")

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    with (OUTPUT_DIR / f"{stamp}_field_presence.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(report)


if __name__ == "__main__":
    run()
