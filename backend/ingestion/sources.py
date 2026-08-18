import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_ROOT = Path("/home/eliedl/data/CIS")

_REV_RANK = {"a": 0, "b": 1, "c": 2}

# T1 for archives whose filename carries no time: the CIS daily snapshot is 18:00 UTC.
_SNAPSHOT_HOUR = 18
_SNAPSHOT_MINUTE = 0

KEEP_FIELDS = frozenset({
    "POLY_TYPE",
    "CT", "CA", "CB", "CC", "CN",
    "SA", "SB", "SC", "CD",
    "FA", "FB", "FC",
    "geometry",
})

# --- SGRDA ---

_SGRDA_CLEAN_RE = re.compile(
    r"^cis_SGRDA(?P<region>GULF|WIS28)_(?P<date>\d{8})(T(?P<hour>\d{2})(?P<minute>\d{2})Z)?_pl_(?P<rev>[abc])\.tar$",
    re.IGNORECASE,
)

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


@dataclass(frozen=True)
class _ChartFile:
    """One archive selected for ingestion."""
    path: Path
    region_code: str
    date_str: str
    hour: int = _SNAPSHOT_HOUR
    minute: int = _SNAPSHOT_MINUTE
    rev: int = 0

    @classmethod
    def from_match(cls, path: Path, m: re.Match) -> "_ChartFile":
        """Build from a clean-filename match; absent time groups fall back to the snapshot hour."""
        groups = m.groupdict()
        return cls(
            path=path,
            region_code=m.group("region").upper(),
            date_str=m.group("date"),
            hour=int(groups["hour"]) if groups.get("hour") else _SNAPSHOT_HOUR,
            minute=int(groups["minute"]) if groups.get("minute") else _SNAPSHOT_MINUTE,
            rev=_REV_RANK[m.group("rev").lower()],
        )

    @property
    def key(self) -> tuple[str, str]:
        """Chart identity — the discovery-side mirror of the DB natural key (T1, region)."""
        return (self.region_code, self.date_str)

    @property
    def t1(self) -> datetime:
        d = self.date_str
        return datetime(
            int(d[:4]), int(d[4:6]), int(d[6:]),
            self.hour, self.minute, 0, tzinfo=timezone.utc,
        )


@dataclass
class ChartSource:
    """
    Discovers archives for one chart type.

    clean_res:         patterns for final-published archives (c > b > a revision ranking).
                       Tried in order; first match wins.
    suffix_fallbacks:  hand-curated archives for the dates that have no clean file at all
                       (DEC-030). One across the whole archive.
    file_globs:        shell globs used to enumerate candidates in each directory.
    region_label_map:  maps regex-captured region code (uppercase) to the DB label string.
    """
    label: str
    table: str
    keep_fields: frozenset
    directories: list[Path]
    clean_res: list[re.Pattern]
    region_label_map: dict[str, str]
    file_globs: tuple[str, ...] = ("*.tar",)
    suffix_fallbacks: tuple[_ChartFile, ...] = ()

    def discover(self) -> list[tuple[Path, datetime, str]]:
        best: dict[tuple[str, str], _ChartFile] = {}
        for directory in self.directories:
            for glob_pat in self.file_globs:
                for path in directory.glob(glob_pat):
                    chart = self._match_clean(path)
                    if chart is None:
                        continue  # timestamped production saves match nothing and are skipped
                    if chart.key not in best or chart.rev > best[chart.key].rev:
                        best[chart.key] = chart

        for fallback in self.suffix_fallbacks:
            if fallback.key in best:
                raise ValueError(
                    f"{self.label}: a clean archive now exists for {fallback.key}; "
                    f"drop {fallback.path.name} from suffix_fallbacks"
                )
            log.warning("Suffix fallback for %s %s: %s",
                        fallback.region_code, fallback.date_str, fallback.path.name)

        selected = sorted([*best.values(), *self.suffix_fallbacks], key=lambda c: c.t1)
        return [(c.path, c.t1, self.region_label_map[c.region_code]) for c in selected]

    def _match_clean(self, path: Path) -> _ChartFile | None:
        for clean_re in self.clean_res:
            m = clean_re.match(path.name)
            if m:
                return _ChartFile.from_match(path, m)
        return None


_SGRDA_SUFFIX_FALLBACKS = (
    _ChartFile(
        path=DATA_ROOT / "SGRDA" / "GULF" / "cis_SGRDAGULF_20190319T1800Z_pl_a_20190319163656.tar",
        region_code="GULF",
        date_str="20190319",
    ),
)

SGRDA_SOURCE = ChartSource(
    label="SGRDA",
    table="sgrda",
    keep_fields=KEEP_FIELDS,
    directories=[DATA_ROOT / "SGRDA" / "GULF", DATA_ROOT / "SGRDA" / "WIS28"],
    clean_res=[_SGRDA_CLEAN_RE],
    region_label_map={"GULF": "gulf", "WIS28": "wis28"},
    suffix_fallbacks=_SGRDA_SUFFIX_FALLBACKS,
)

SGRDR_SOURCE = ChartSource(
    label="SGRDR",
    table="sgrdr",
    keep_fields=KEEP_FIELDS,
    directories=[DATA_ROOT / "SGRDR" / "EC"],
    clean_res=[_SGRDR_OLD_CLEAN_RE, _SGRDR_NEW_CLEAN_RE],
    region_label_map={"EC": "ec"},
    file_globs=("*.tar", "*.zip"),
)
