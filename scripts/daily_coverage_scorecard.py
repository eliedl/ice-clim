"""
daily_coverage_scorecard.py
----------------------------
Generates a scorecard heatmap showing which days have a GEC_D_* daily ice chart
in the CIS archive.

- Columns : winter seasons (e.g. "2008-09"), one per season
            Sep-Dec come from year n-1; Jan-Aug come from year n
- Rows    : day within the season (Sep 1 at top -> Aug 31 at bottom),
            trimmed to the observed date range (first -> last row with any data)
- Color   : present (blue) / absent (light gray)

Output: docs/daily_coverage_scorecard.png
"""

import os
import glob
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.colors import ListedColormap

# ── Config ──────────────────────────────────────────────────────────────────
ARCHIVE_ROOT = r"C:\Users\dumas\Documents\archive\ice-raw-data-MPO"
OUTPUT_PATH  = r"C:\Users\dumas\Documents\perso\ice-clim\docs\daily_coverage_scorecard.png"

# Seasons: "YYYY-YY" where n-1 = first year, n = second year
# Season 2008-09 -> Sep-Dec 2008 + Jan-Aug 2009
# Season 2019-20 -> Sep-Dec 2019 + Jan-Aug 2020
SEASON_N_START = 2009   # 'n' (Jan-Aug side) of first season
SEASON_N_END   = 2020   # 'n' (Jan-Aug side) of last season

# ── 1. Collect all dates that have a GEC_D_ shapefile ───────────────────────
# Scan both n-1 and n years
scan_start = SEASON_N_START - 1   # 2008
scan_end   = SEASON_N_END         # 2020

print("Scanning archive for GEC_D_* shapefiles ...")
daily_dates: set[date] = set()

for year in range(scan_start, scan_end + 1):
    pattern = os.path.join(ARCHIVE_ROOT, f"{year}????", "GEC_D_*.shp")
    for path in glob.glob(pattern):
        folder = os.path.basename(os.path.dirname(path))
        try:
            d = date(int(folder[:4]), int(folder[4:6]), int(folder[6:8]))
            daily_dates.add(d)
        except ValueError:
            pass

print(f"  Found {len(daily_dates)} dates ({scan_start}-{scan_end})")

# ── 2. Build season row template: Sep 1 -> Aug 31 (365 rows, no Feb 29) ─────
# Use a non-leap reference year to avoid Feb 29 complications; we handle
# Feb 29 per-season when building the matrix.
REF_YEAR = 2001   # non-leap
sep_aug: list[date] = []
for month in [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]:
    year = REF_YEAR if month >= 9 else REF_YEAR + 1
    m_start = date(year, month, 1)
    # iterate days in that month
    d = m_start
    while d.month == month:
        sep_aug.append(d)
        d += timedelta(days=1)

N_ROWS = len(sep_aug)   # 365

# ── 3. Build seasons list and the matrix ────────────────────────────────────
seasons = list(range(SEASON_N_START, SEASON_N_END + 1))   # n values
n_seasons = len(seasons)

matrix = np.zeros((N_ROWS, n_seasons), dtype=np.float32)

for si, n in enumerate(seasons):
    n_prev = n - 1
    for ri, ref_day in enumerate(sep_aug):
        # Sep-Dec -> year n-1 ;  Jan-Aug -> year n
        actual_year = n_prev if ref_day.month >= 9 else n
        try:
            actual = date(actual_year, ref_day.month, ref_day.day)
        except ValueError:
            continue   # Feb 29 in a non-leap actual year
        if actual in daily_dates:
            matrix[ri, si] = 1.0

# ── 4. No trimming — show full Sep 1 -> Aug 31 ──────────────────────────────
matrix_crop = matrix
days_crop   = sep_aug
n_crop      = N_ROWS

print(f"  Y-axis: {days_crop[0]:%b %d} -> {days_crop[-1]:%b %d}  ({n_crop} rows)")

# ── 5. Monthly tick positions ────────────────────────────────────────────────
month_ticks  = []
month_labels = []
prev_month   = None
for i, d in enumerate(days_crop):
    if d.month != prev_month:
        month_ticks.append(i)
        month_labels.append(d.strftime("%b"))
        prev_month = d.month

# ── 6. Season labels (x-axis): "2008-09", "2009-10", ... ────────────────────
def season_label(n):
    return f"{n-1}-{str(n)[2:]}"

season_labels = [season_label(n) for n in seasons]

# ── 7. Draw the heatmap ──────────────────────────────────────────────────────
fig_h = max(8, n_crop * 0.05)
fig_w = max(8, n_seasons * 0.85)

fig, ax = plt.subplots(figsize=(fig_w, fig_h))

cmap = ListedColormap(["#e8e8e8", "#2471a3"])

ax.imshow(
    matrix_crop,
    aspect="auto",
    cmap=cmap,
    vmin=0, vmax=1,
    origin="upper",
    interpolation="none",
)

# x-axis: season labels
ax.set_xticks(range(n_seasons))
ax.set_xticklabels(season_labels, rotation=45, ha="right", fontsize=9)
ax.xaxis.set_tick_params(length=0)

# y-axis: month labels
ax.set_yticks(month_ticks)
ax.set_yticklabels(month_labels, fontsize=9)
ax.yaxis.set_tick_params(length=0)

# Horizontal grid lines at month boundaries
for t in month_ticks:
    ax.axhline(t - 0.5, color="white", linewidth=1.0)

# Vertical grid lines between seasons
for xi in range(n_seasons - 1):
    ax.axvline(xi + 0.5, color="white", linewidth=0.8)

# Per-season coverage % annotation (above columns)
for si in range(n_seasons):
    col = matrix_crop[:, si]
    pct = 100 * col.sum() / n_crop
    ax.text(si, -1.5, f"{pct:.0f}%", ha="center", va="bottom", fontsize=7.5, color="#333")

# Legend
patch_present = mpatches.Patch(color="#2471a3", label="Daily chart present (GEC_D_*)")
patch_absent  = mpatches.Patch(color="#e8e8e8", label="No daily chart")
ax.legend(handles=[patch_present, patch_absent], loc="lower right",
          fontsize=8, framealpha=0.9)

ax.set_xlabel("Winter season", fontsize=10, labelpad=28)
ax.set_title(
    "CIS Daily Ice Chart Coverage  (GEC_D_*)\n"
    "Gulf of St. Lawrence  --  seasons 2008-09 to 2019-20",
    fontsize=12, fontweight="bold", pad=10,
)

plt.tight_layout()
plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
print(f"Saved -> {OUTPUT_PATH}")
