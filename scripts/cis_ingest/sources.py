import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_ROOT = Path("/home/eliedl/data")

_REV_RANK = {"a": 0, "b": 1, "c": 2}

_SGRDA_CLEAN_RE = re.compile(
    r"^cis_SGRDA(GULF|WIS28)_(\d{8})(T(\d{2})(\d{2})Z)?_pl_([abc])\.tar$",
    re.IGNORECASE,
)
_SGRDA_SUFFIX_RE = re.compile(
    r"^cis_SGRDA(GULF|WIS28)_(\d{8})(T(\d{2})(\d{2})Z)?_pl_([abc])_(\d{14})\.tar$",
    re.IGNORECASE,
)

SGRDA_KEEP = frozenset({
    "POLY_TYPE",
    "CT", "CA", "CB", "CC", "CN",
    "SA", "SB", "SC", "CD",
    "FA", "FB", "FC", "CF",
    "geometry",
})


@dataclass
class ChartSource(ABC):
    label: str
    table: str
    keep_fields: frozenset

    @abstractmethod
    def discover(self) -> list[tuple[Path, datetime, str]]:
        ...


@dataclass
class SGRDASource(ChartSource):
    """
    SGRDA chart source (Gulf and WIS28 regions, co-located in one directory).

    Revision selection: highest-revision clean archive (c > b > a) per chart date.
    Fallback: most-recent timestamped-suffix archive, only when no clean version
    exists for that date (2 known cases in the full dataset).
    """
    directory: Path
    clean_re: re.Pattern
    suffix_re: re.Pattern

    def discover(self) -> list[tuple[Path, datetime, str]]:
        best_clean: dict = {}
        suffix_by_date: dict = defaultdict(list)

        for tar_path in self.directory.glob("*.tar"):
            m = self.clean_re.match(tar_path.name)
            if m:
                region_code = m.group(1).upper()
                date_str    = m.group(2)
                hour        = int(m.group(4)) if m.group(4) else 18
                minute      = int(m.group(5)) if m.group(5) else 0
                rev         = _REV_RANK[m.group(6).lower()]
                key = (region_code, date_str)
                if key not in best_clean or rev > best_clean[key][0]:
                    best_clean[key] = (rev, hour, minute, tar_path)
                continue

            m = self.suffix_re.match(tar_path.name)
            if m:
                region_code = m.group(1).upper()
                date_str    = m.group(2)
                hour        = int(m.group(4)) if m.group(4) else 18
                minute      = int(m.group(5)) if m.group(5) else 0
                rev         = _REV_RANK[m.group(6).lower()]
                ts          = m.group(7)
                suffix_by_date[(region_code, date_str)].append(
                    (rev, ts, hour, minute, tar_path)
                )

        results = []

        for (region_code, date_str), (_, hour, minute, tar_path) in best_clean.items():
            results.append((tar_path, _parse_t1(date_str, hour, minute), _label(region_code)))

        for (region_code, date_str), sfx_list in suffix_by_date.items():
            if (region_code, date_str) in best_clean:
                continue
            _, ts, hour, minute, tar_path = max(sfx_list, key=lambda x: (x[0], x[1]))
            t1 = _parse_t1(date_str, hour, minute)
            results.append((tar_path, t1, _label(region_code)))
            log.warning("Suffix fallback for %s %s: %s", region_code, date_str, tar_path.name)

        results.sort(key=lambda x: x[1])
        return results


def _parse_t1(date_str: str, hour: int, minute: int) -> datetime:
    return datetime(
        int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
        hour, minute, 0, tzinfo=timezone.utc,
    )


def _label(region_code: str) -> str:
    return "gulf" if region_code == "GULF" else "wis28"


SGRDA_SOURCE = SGRDASource(
    label="SGRDA",
    table="sgrda",
    keep_fields=SGRDA_KEEP,
    directory=DATA_ROOT / "SGRDA" / "wis28",
    clean_re=_SGRDA_CLEAN_RE,
    suffix_re=_SGRDA_SUFFIX_RE,
)
