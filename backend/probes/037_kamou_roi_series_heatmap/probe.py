"""Probe 037 — the kamou-roi series CSV as a winters x days heatmap.

Probe 035's CSV is a (winters, days) table of ice-covered area in km2 — the shape `imshow`
draws directly, one pixel per chart-day. Read as a grid rather than as 20 overplotted
curves, three things that a series panel buries become the figure's subject:

  - **where the record is missing**. A quarter of the table is empty, and the preamble is
    explicit that an empty cell is a day no chart was published, not a day without ice. The
    holes are left unpainted and show the ocean background through, so a gap in the archive
    can never be mistaken for the ramp's low end.
  - **the season envelope**, as the diagonal edges of the painted block: the winters that
    froze early or cleared late read off the left and right margins at a glance.
  - **the mid-winter sub-threshold days** probe 036 measured as a 15 d gap between the
    ice-day count and the freeze-up/break-up interval — here they are the dark streaks
    *inside* an otherwise full winter.

The CSV is the only input: the figure's title, period, source and cell size are parsed from
the file's own `#` preamble rather than rebuilt from the region table, so the probe draws
any 035 export and stays decoupled from `climatology/core/regions.py`. Labels are French
because the strings it carries are — the CSV is a standalone French deliverable.

Read-only: one CSV. No DB, no archive, no region geometry.

Run:
    .venv/bin/python -m backend.probes.037_kamou_roi_series_heatmap.probe
    .venv/bin/python -m backend.probes.037_kamou_roi_series_heatmap.probe --csv path/to/other.csv
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from climatology.plot.colors import (
    DARK_FG, DARK_LINE, DARK_MUTED, DARK_OCEAN, build_cmap, style_axes, style_colorbar,
)
from climatology.plot.kinds import RAW
from climatology.services.calendar import month_start, season_day_label

OUTPUT_DIR = Path(__file__).parent / "output"

CSV = Path("backend/probes/035_kamou_roi_series_csv/output/"
           "2026-09-30_145810_concentration_kamou-roi_2007-2026_sgrda_series_"
           "20260929-141853-488414.csv")

N_COLORBAR_TICKS = 6

# A preamble entry is `# KEY<2+ spaces>value`. The single space after `#` is what separates a
# key line from a continuation line, which is indented further and must not read as a key.
PREAMBLE_ENTRY = re.compile(r"^#\s(\S+)\s{2,}(.+?)\s*$")


def _preamble(path: Path) -> tuple[str, dict[str, str]]:
    """The CSV's `#` header as (title, entries): its first line, then the `KEY value` pairs.

    The title is the only line carrying no key, so it is taken positionally rather than
    matched. Entries are indexed, not `.get`-ed, by the callers: one writer emits this
    preamble, so a missing key means the file is not an 035 export and should fail loudly.
    """
    title, entries = "", {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        if not title:
            title = line.lstrip("# ").rstrip(".")
            continue
        if match := PREAMBLE_ENTRY.match(line):
            entries[match.group(1)] = match.group(2)
    return title, entries


def _frame(path: Path) -> pd.DataFrame:
    """The table as the preamble's own LECTURE line prescribes, with the day axis as integers.

    CSV carries no types, so the `day_of_season` header level reads back as strings; it is
    an ordinal and is used for arithmetic here, so it is cast on the way in.
    """
    df = pd.read_csv(path, comment="#", header=[0, 1], index_col=0)
    df.columns = df.columns.set_levels(
        df.columns.levels[1].astype(int), level="day_of_season")
    return df


def _month_ticks(days: np.ndarray) -> tuple[list[int], list[str]]:
    """Column positions and MM-DD labels of the month starts the day axis spans.

    Positions are resolved by `searchsorted`, not by `day - days[0]`: a month start need not
    itself be an observed day — a weekly export lands on one roughly once a year — and the
    nearest following column is where its label belongs.
    """
    starts = sorted({month_start(int(day)) for day in days} - {month_start(int(days[0]))})
    starts = [month_start(int(days[0])), *starts]
    positions = [int(np.searchsorted(days, start)) for start in starts]
    return positions, [season_day_label(start) for start in starts]


def _figure(df: pd.DataFrame, title: str, entries: dict[str, str],
            csv_name: str, path: Path) -> None:
    """One heatmap panel: winters down the rows, days of season across, km2 in the cells."""
    days = df.columns.get_level_values("day_of_season").to_numpy()
    seasons = df.index.to_numpy()
    # Masked, not filled: an unpainted pixel shows the ocean facecolor through, keeping a
    # missing chart visually disjoint from the ramp a real 0.0 km2 is drawn on.
    values = np.ma.masked_invalid(df.to_numpy(dtype=float))
    cmap, norm = build_cmap(RAW, vmin=0.0, vmax=float(values.max()))

    fig, ax = plt.subplots(figsize=(13.0, 5.6), facecolor=DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)
    im = ax.imshow(values, cmap=cmap, norm=norm, aspect="auto", interpolation="none")
    # Before the tick labels, not after: `style_axes` runs `ticklabel_format`, which only
    # accepts the default numeric formatter, and fixed labels replace it.
    style_axes(ax)

    positions, labels = _month_ticks(days)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_yticks(np.arange(len(seasons)))
    ax.set_yticklabels(seasons)
    for position in positions[1:]:
        ax.axvline(position - 0.5, color=DARK_LINE, lw=0.6, alpha=0.8, zorder=3)
    # Separators on the cell edges, so a row reads as one winter rather than as a band of
    # the field — the y axis is categorical, unlike the calendar axis it is crossed with.
    ax.set_yticks(np.arange(len(seasons) + 1) - 0.5, minor=True)
    ax.grid(which="minor", axis="y", color=DARK_LINE, lw=0.5, alpha=0.6)
    ax.tick_params(which="minor", length=0)

    ax.set_xlabel("jour de saison (origine 09-01)", color=DARK_FG)
    ax.set_ylabel("hiver (année de fin)", color=DARK_FG)
    ax.set_title(f"{entries['Région']} — {entries['Période']}\n{title}",
                 color=DARK_FG, fontsize=12, pad=12)

    legend = ax.legend(handles=[Patch(facecolor=DARK_OCEAN, edgecolor=DARK_LINE,
                                     label="aucune carte publiée ce jour-là")],
                       loc="upper right", facecolor=DARK_OCEAN, edgecolor=DARK_LINE,
                       fontsize=9, framealpha=0.92)
    for text in legend.get_texts():
        text.set_color(DARK_FG)

    ticks = list(np.linspace(0.0, float(values.max()), N_COLORBAR_TICKS))
    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.055, pad=0.16, aspect=45)
    style_colorbar(cbar, label="superficie de glace (km²)", tick_values=ticks,
                   tick_labels=[f"{tick:.1f}" for tick in ticks])

    fig.text(0.012, 0.012, f"probe 037 · {csv_name} · {entries['Source']}",
             color=DARK_MUTED, fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=CSV)
    args = parser.parse_args()

    title, entries = _preamble(args.csv)
    df = _frame(args.csv)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure_path = OUTPUT_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}_series_heatmap.png"
    _figure(df, title, entries, args.csv.name, figure_path)

    days = df.columns.get_level_values("day_of_season")
    print(f"read       {args.csv}")
    print(f"region     {entries['Région']} — {entries['Période']} ({entries['Source']})")
    print(f"table      {len(df.index)} winters x {len(df.columns)} days "
          f"(day {days[0]} {season_day_label(days[0])} "
          f"to {days[-1]} {season_day_label(days[-1])})")
    print(f"values     0 to {np.nanmax(df.to_numpy()):.4f} km², "
          f"{df.isna().to_numpy().mean():.1%} of cells carry no chart")
    print(f"written    {figure_path}")


if __name__ == "__main__":
    main()
