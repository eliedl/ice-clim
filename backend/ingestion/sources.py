import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_ROOT = Path("/home/eliedl/data/CIS")

_REV_RANK = {"a": 0, "b": 1, "c": 2}

# --- SGRDA ---

_SGRDA_CLEAN_RE = re.compile(
    r"^cis_SGRDA(?P<region>GULF|WIS28)_(?P<date>\d{8})(T(?P<hour>\d{2})(?P<minute>\d{2})Z)?_pl_(?P<rev>[abc])\.tar$",
    re.IGNORECASE,
)
_SGRDA_SUFFIX_RE = re.compile(
    r"^cis_SGRDA(?P<region>GULF|WIS28)_(?P<date>\d{8})(T(?P<hour>\d{2})(?P<minute>\d{2})Z)?_pl_(?P<rev>[abc])_(?P<ts>\d{14})\.tar$",
    re.IGNORECASE,
)

SGRDA_KEEP = frozenset({
    "POLY_TYPE",
    "CT", "CA", "CB", "CC", "CN",
    "SA", "SB", "SC", "CD",
    "FA", "FB", "FC",
    "geometry",
})

# --- SGRDR ---

# Era 1 (1968–2019): ZIP, date-only, pl_a only, NAD27 → reproject on ingest
_SGRDR_OLD_CLEAN_RE = re.compile(
    r"^CIS_(?P<region>EC)_(?P<date>\d{8})_pl_(?P<rev>a)\.zip$",
    re.IGNORECASE,
)
# Era 2 (2020–present): TAR, optional timestamp, pl_a/b/c, WGS84 → reproject on ingest
_SGRDR_NEW_CLEAN_RE = re.compile(
    r"^cis_SGRDR(?P<region>EC)_(?P<date>\d{8})(T(?P<hour>\d{2})(?P<minute>\d{2})Z)?_pl_(?P<rev>[abc])\.tar$",
    re.IGNORECASE,
)
_SGRDR_NEW_SUFFIX_RE = re.compile(
    r"^cis_SGRDR(?P<region>EC)_(?P<date>\d{8})(T(?P<hour>\d{2})(?P<minute>\d{2})Z)?_pl_(?P<rev>[abc])_(?P<ts>\d{14})\.tar$",
    re.IGNORECASE,
)

# See SGRDR*.xml to see a compete list of the attributes
SGRDR_KEEP = frozenset({
    "POLY_TYPE",
    "CT", "CA", "CB", "CC", "CN",
    "SA", "SB", "SC", "CD",
    "FA", "FB", "FC",
    "geometry",
})


@dataclass
class ChartSource:
    """
    Discovers archives for one chart type.

    clean_res:         patterns for final-published archives (c > b > a revision ranking).
                       Tried in order; first match wins.
    suffix_res:        patterns for timestamped-suffix production saves (fallback only when
                       no clean archive exists for that date).
    file_globs:        shell globs used to enumerate candidates in each directory.
    region_label_map:  maps regex-captured region code (uppercase) to the DB label string.
    """
    label: str
    table: str
    keep_fields: frozenset
    directories: list[Path]
    clean_res: list[re.Pattern]
    suffix_res: list[re.Pattern]
    region_label_map: dict[str, str]
    file_globs: tuple[str, ...] = ("*.tar",)

    def discover(self) -> list[tuple[Path, datetime, str]]:
        best_clean: dict = {}
        suffix_by_date: dict = defaultdict(list)

        for directory in self.directories:
            for glob_pat in self.file_globs:
                for path in directory.glob(glob_pat):
                    for clean_re in self.clean_res:
                        m = clean_re.match(path.name)
                        if m:
                            region_code = m.group("region").upper()
                            date_str    = m.group("date")
                            hour        = int(m.group("hour"))   if m.groupdict().get("hour")   else 18
                            minute      = int(m.group("minute")) if m.groupdict().get("minute") else 0
                            rev         = _REV_RANK[m.group("rev").lower()]
                            key = (region_code, date_str)
                            if key not in best_clean or rev > best_clean[key][0]:
                                best_clean[key] = (rev, hour, minute, path)
                            break
                    else:
                        for suffix_re in self.suffix_res:
                            m = suffix_re.match(path.name)
                            if m:
                                region_code = m.group("region").upper()
                                date_str    = m.group("date")
                                hour        = int(m.group("hour"))   if m.group("hour")   else 18
                                minute      = int(m.group("minute")) if m.group("minute") else 0
                                rev         = _REV_RANK[m.group("rev").lower()]
                                ts          = m.group("ts")
                                suffix_by_date[(region_code, date_str)].append(
                                    (rev, ts, hour, minute, path)
                                )
                                break

        results = []

        for (region_code, date_str), (_, hour, minute, path) in best_clean.items():
            results.append((path, _parse_t1(date_str, hour, minute), self.region_label_map[region_code]))

        for (region_code, date_str), sfx_list in suffix_by_date.items():
            if (region_code, date_str) in best_clean:
                continue
            _, ts, hour, minute, path = max(sfx_list, key=lambda x: (x[0], x[1]))
            results.append((path, _parse_t1(date_str, hour, minute), self.region_label_map[region_code]))
            log.warning("Suffix fallback for %s %s: %s", region_code, date_str, path.name)

        results.sort(key=lambda x: x[1])
        return results


def _parse_t1(date_str: str, hour: int, minute: int) -> datetime:
    return datetime(
        int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
        hour, minute, 0, tzinfo=timezone.utc,
    )


SGRDA_SOURCE = ChartSource(
    label="SGRDA",
    table="sgrda",
    keep_fields=SGRDA_KEEP,
    directories=[DATA_ROOT / "SGRDA" / "GULF", DATA_ROOT / "SGRDA" / "WIS28"],
    clean_res=[_SGRDA_CLEAN_RE],
    suffix_res=[_SGRDA_SUFFIX_RE],
    region_label_map={"GULF": "gulf", "WIS28": "wis28"},
)

SGRDR_SOURCE = ChartSource(
    label="SGRDR",
    table="sgrdr",
    keep_fields=SGRDR_KEEP,
    directories=[DATA_ROOT / "SGRDR" / "EC"],
    clean_res=[_SGRDR_OLD_CLEAN_RE, _SGRDR_NEW_CLEAN_RE],
    suffix_res=[_SGRDR_NEW_SUFFIX_RE],
    region_label_map={"EC": "ec"},
    file_globs=("*.tar", "*.zip"),
)
