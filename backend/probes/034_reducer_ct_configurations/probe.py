"""Probe 034 — the CT configurations behind the reducer disagreements.

`season_duration_10` on manicouagan / sgrdr / 1991-2020, `mediantt` as the reference.
Both candidates move whole chart weeks (every delta is a multiple of 7), so their delta
fields are lattices; this probe takes the **largest coherent patch at each end of each
lattice** and prints the season x day CT matrix those cells carry.

The question it answers is *why* the orders disagree, not *by how much*: the delta maps
already carry the magnitudes. A tail patch is the extreme case, so its matrix is the
configuration that separates the reducers most cleanly.

Design under test (see README):
  - a group is a *connected patch* of one delta value, not the delta value itself (probe
    027's patch rule, keyed to the lattice). A delta value is an equivalence class
    scattered over the basin — many configurations shift a cell by one chart week — so
    only a patch is a place with a configuration to read;
  - the report prints the per-season step counts beside the matrix, so the arithmetic
    each reducer performs is visible next to the product values it produced.

Read-only on the archives; one DB fetch for the CT matrices.

Run:
    .venv/bin/python -m backend.probes.034_reducer_ct_configurations.probe
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
from dotenv import load_dotenv
from scipy import ndimage

load_dotenv(Path(__file__).parents[3] / ".env")

from climatology.pipeline import _fetch, _resolve
from climatology.core.context import RunContext
from climatology.core.metrics import Metric
from climatology.core.reduction.temporal import (
    MPO_MIN_SEASON_COVERAGE,
    _stream_day_stacks,
)
from climatology.core.regions import Tier
from climatology.services.calendar import SEASON_ORIGIN, filter_admissible_days
from climatology.core.export import find_archived
from climatology.tests.diff_map_regression_test import Product, _stats
from climatology.utils._types import WetVector
from climatology.utils.arithmetics import _nanmean, _nanmedian_high

OUTPUT_DIR = Path(__file__).parent / "output"

# --- 1. The product registry under test ---------------------------------------

METRIC = "season_duration_10"
REGION, SOURCE, PERIOD, TIER = "golfe", "sgrdr", "1991-2020", "full"
BASELINE = "mediantt"
CANDIDATES = ("ttmedian",)

CT_THRESHOLD = 0.1   # season_duration_10 counts days at or above 1/10

# Tail groups on this metric run 10 to 924 cells; the uniformity check needs a sample,
# not a census, and 200 keeps the burned cube small enough to hold per group.
GROUP_SAMPLE = 200


# --- 2. Retrieve the archived rasters -----------------------------------------

def context(reduction: str) -> RunContext:
    """The run identity of one reduction — what the archive is keyed on."""
    return _resolve(METRIC, REGION, SOURCE, PERIOD, reduction)


def product(ctx: RunContext) -> Product:
    """The newest archived raster for one run identity, selected on its manifest."""
    npz, _ = next((npz, m) for npz, m in find_archived(ctx) if m["tier"] == TIER)
    return Product(npz)


# --- 3. Diff a candidate against the baseline ---------------------------------

def delta(base: Product, cand: Product) -> np.ndarray:
    """Candidate − baseline, NaN wherever either product is undefined."""
    s = _stats(base.values, cand.aligned_to(base))
    return np.where(s["both"], s["diff"], np.nan)


# --- 4. Isolate coherent patches at the tails of the delta lattice ------------

# Probe 027's patch rule, keyed to the delta lattice instead of a magnitude cut. A delta
# value is an equivalence class scattered over the basin — many configurations shift a cell
# by one chart week — so a *connected* patch of one value is what shares a configuration.
PATCH_INTERIOR = 3    # cells of clearance from the wet-mask edge, to exclude the coastal band
MIN_PATCH_CELLS = 5   # below this a component is speckle, not a place


@dataclass(frozen=True)
class Group:
    """One coherent patch of cells that a candidate moves by the same amount."""

    candidate: str
    delta: float
    mask: np.ndarray            # (H, W) bool

    @property
    def label(self) -> str:
        return f"{self.candidate} {self.delta:+.0f} d"

    @property
    def n_cells(self) -> int:
        return int(self.mask.sum())

    @property
    def cell(self) -> int:
        """Flat index of the patch's representative cell — the report's matrix and the map's marker."""
        return int(np.argmax(self.mask.ravel()))


def _largest_patch(candidate: str, d: np.ndarray, interior: np.ndarray,
                   lattice: np.ndarray) -> Group:
    """The biggest connected patch at the first lattice value that carries one, walking inward."""
    for v in lattice:
        labels, n = ndimage.label((d == v) & interior)
        sizes = np.bincount(labels.ravel(), minlength=n + 1)
        sizes[0] = 0                                  # label 0 is the background
        if n and sizes.max() >= MIN_PATCH_CELLS:
            return Group(candidate, float(v), labels == int(sizes.argmax()))


def tail_patches(candidate: str, d: np.ndarray, wet: np.ndarray) -> list[Group]:
    """The largest coherent patch at each end of this candidate's delta lattice.

    The extreme values are often speckle once the coastal band is excluded, so each end
    walks inward until a lattice value carries a patch worth inspecting.
    """
    interior = ndimage.distance_transform_edt(wet) >= PATCH_INTERIOR
    lattice = np.unique(d[np.isfinite(d)])
    return [_largest_patch(candidate, d, interior, lattice),
            _largest_patch(candidate, d, interior, lattice[::-1])]


# --- 5. Locate the groups on the map ------------------------------------------

def groups_png(deltas: dict[str, np.ndarray], groups: list[Group], path: Path) -> None:
    """One panel per candidate: its delta field, with each inspected patch outlined and marked."""
    fig, axes = plt.subplots(1, len(deltas), figsize=(7 * len(deltas), 6), dpi=150)
    for ax, (candidate, d) in zip(np.atleast_1d(axes), deltas.items()):
        lim = float(np.nanmax(np.abs(d)))
        im = ax.imshow(d, cmap="RdBu_r", vmin=-lim, vmax=lim, interpolation="nearest")
        fig.colorbar(im, ax=ax, shrink=0.8, label=f"{candidate} − {BASELINE} (days)")
        for i, g in enumerate([g for g in groups if g.candidate == candidate], start=1):
            row, col = np.unravel_index(g.cell, g.mask.shape)
            ax.contour(g.mask.astype(float), levels=[0.5], colors="#111111", linewidths=1.0)
            ax.plot(col, row, "o", mfc="none", mec="#111111", ms=13, mew=1.6,
                    label=f"[{i}] {g.delta:+.0f} d — {g.n_cells} cells")
            ax.annotate(str(i), (col, row), textcoords="offset points", xytext=(11, 7),
                        fontsize=9, fontweight="bold", color="#111111")
        ax.set_title(candidate, fontsize=11)
        ax.legend(loc="lower right", fontsize=8)
    fig.suptitle(f"{METRIC} — largest coherent patch at each end of the delta lattice "
                 f"({REGION}, {PERIOD})\ncircle = the cell whose CT matrix is printed")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# --- 5b. Which statistic leads, per day, against the shape of the sample ------

# Does the ordering of mean and median follow the shape of the season sample? The violins
# put the two statistics on top of the distribution they are computed from, so a case
# label can be read against the sample's skew and modality rather than asserted.
CASE_COLOURS = {"mean > median": "#d1495b", "equal": "#8d99ae", "median > mean": "#3d6cb9"}


def leading_stat(mean: WetVector, median: WetVector) -> np.ndarray:
    """Which of the two statistics leads at each day — the three orderings, as labels."""
    return np.where(mean == median, "equal",
                    np.where(mean > median, "mean > median", "median > mean"))


def cases_png(matrix: np.ndarray, days: list[int], group: Group, path: Path) -> None:
    """Per-day violin of the season CT sample, coloured by which statistic leads.

    A violin needs spread: the ice-free days are a constant sample, on which the kernel
    density estimate is singular, so those are left to the mean/median markers alone.
    """
    mean, median = _nanmean(matrix), _nanmedian_high(matrix)
    case = leading_stat(mean, median)
    x = np.arange(len(days))
    spread = np.nanstd(matrix, axis=0) > 0

    fig, ax = plt.subplots(figsize=(17, 6), dpi=150)
    parts = ax.violinplot([matrix[np.isfinite(matrix[:, i]), i] for i in x[spread]],
                          positions=x[spread], widths=0.9, showextrema=False)
    for body, i in zip(parts["bodies"], x[spread]):
        body.set_facecolor(CASE_COLOURS[case[i]])
        body.set_alpha(0.8)
    ax.plot(x, median, "_", color="#111111", ms=12, mew=2.0, label="median = sorted[n//2]")
    ax.plot(x, mean, ".", color="#f0a202", ms=8, label="mean")
    ax.axhline(CT_THRESHOLD, color="#111111", lw=1.1, ls="--",
               label=f"threshold {CT_THRESHOLD:g} — only crossings here change the duration")

    counts = {c: int((case == c).sum()) for c in CASE_COLOURS}
    ax.legend(handles=[Patch(facecolor=v, alpha=0.8, label=f"{k}  ({counts[k]} d)")
                       for k, v in CASE_COLOURS.items()] + ax.get_legend_handles_labels()[0],
              loc="upper right", fontsize=9)
    ax.set_xticks(x[::4])
    ax.set_xticklabels([(SEASON_ORIGIN + timedelta(days=int(d) - 1)).strftime("%b %d")
                        for d in np.array(days)[::4]], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("CT (fraction)")
    ax.set_title(f"{METRIC} — season CT sample per day, patch {group.label}\n"
                 f"{matrix.shape[0]} seasons x {matrix.shape[1]} admissible days "
                 f"({group.n_cells} cells)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# --- 6. The CT matrix each group's cells carry --------------------------------

def wet_columns(group: Group, tier: Tier, rng) -> np.ndarray:
    """Wet-vector columns for a sample of the group's cells — the burn's own indexing."""
    index = np.full(tier.wet_mask.shape, -1)
    index[tier.wet_mask] = np.arange(int(tier.wet_mask.sum()))
    cols = index[group.mask & tier.wet_mask]
    if cols.size <= GROUP_SAMPLE:
        return cols
    # ``Group.cell`` is the first cell in raster order, and so is ``cols[0]``: keep it there,
    # since the report pairs its matrix with the product values read at that same cell.
    return np.concatenate([cols[:1], rng.choice(cols[1:], GROUP_SAMPLE - 1, replace=False)])


def ct_cube(df, tier: Tier, cols: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """``(n_seasons, n_days, n_cells)`` burned CT for the selected cells, plus the admissible days."""
    days, planes = [], []
    for dos, stack in _stream_day_stacks(df, tier=tier):
        days.append(dos)
        planes.append(stack[:, 0, cols])       # CT is the only value column
    return np.stack(planes, axis=1), days


# --- 7. Do the group's cells all carry the same configuration? ----------------

def distinct_configurations(cube: np.ndarray) -> int:
    """How many different season x day CT matrices the group's cells carry (NaN compares equal)."""
    per_cell = np.nan_to_num(cube, nan=-1.0).reshape(-1, cube.shape[-1]).T
    return len(np.unique(per_cell, axis=0))


# --- 8. Print one matrix per group --------------------------------------------

def _glyph(v: float) -> str:
    """One character per CT: ' ' unobserved, '.' open water, 1-9 full tenths, '#' compact.

    Binned by floor, not to the nearest tenth, so a digit means "at or above that tenth"
    and the row is countable against the kernel's own ``>=`` test. Rounding would bin at
    0.055 and draw a sub-threshold mean of 0.09 as ``1``. The epsilon is for the exact
    codes, stored as float32: 0.7 is 0.69999998 and would otherwise floor to ``6``.
    """
    if not np.isfinite(v):
        return " "
    if v <= 0:
        return "."
    return "#" if v >= 0.95 else str(int(v * 10 + 1e-6))


def _ruler(days: list[int]) -> str:
    """A month tick under the day axis, so a matrix column can be read as a date."""
    return "".join("|" if (SEASON_ORIGIN + timedelta(days=d - 1)).day <= 7 else " "
                   for d in days)


def reducer_arithmetic(cube: np.ndarray, days: list[int], step_days: int) -> dict:
    """What each reducer computes at these cells, driven through the production kernel.

    Nothing here is re-derived: the same ``ThresholdDuration`` fold runs on the raw day
    stacks (threshold-first) and on the statistic-compressed slices (stat-first), so a
    line of the report that disagrees with the product above it is a real discrepancy.
    """
    kernel = Metric.build(METRIC).kernel
    stacks = [(d, cube[:, i, None, :]) for i, d in enumerate(days)]   # (n_seasons, 1, n_cells)
    compressed = lambda stat: (lambda: iter([(d, stat(s)) for d, s in stacks]))
    per_season = kernel.reduce(lambda: iter(stacks)) * step_days      # (n_seasons, n_cells)
    n_valid = np.sum(~np.isnan(per_season), axis=0)
    keep = n_valid >= np.ceil(MPO_MIN_SEASON_COVERAGE * per_season.shape[0])
    return {
        "per_season": per_season,
        "median_series": _nanmedian_high(cube[:, :, 0]),
        "mean_series": _nanmean(cube[:, :, 0]),
        "mediantt": kernel.reduce(compressed(_nanmedian_high))[0] * step_days,
        "meantt": kernel.reduce(compressed(_nanmean))[0] * step_days,
        "ttmedian": _nanmedian_high(per_season)[0] if keep[0] else np.nan,
        "n_valid": int(n_valid[0]),
    }


def group_report(group: Group, cube: np.ndarray, days: list[int], seasons: list[int],
                 *, step_days: int, base: float, cand: float) -> list[str]:
    """The group's CT configuration, with the per-season counts each reducer folds."""
    n_distinct = distinct_configurations(cube)
    matrix = cube[:, :, 0]                                  # the representative cell
    a = reducer_arithmetic(cube, days, step_days)
    per_season, median_series, mean_series = a["per_season"][:, 0], a["median_series"], a["mean_series"]

    lines = [
        f"### {group.label} — {group.n_cells} cells "
        f"({min(group.n_cells, GROUP_SAMPLE)} sampled)",
        f"    distinct CT configurations in the group : {n_distinct}"
        f"{'  <-- NOT uniform' if n_distinct > 1 else '  (uniform)'}",
        f"    product values at these cells           : {BASELINE} {base:g} d, "
        f"{group.candidate} {cand:g} d, delta {group.delta:+g} d",
        f"    matrix                                  : {len(seasons)} seasons x "
        f"{len(days)} admissible days, {a['n_valid']} seasons observed",
        "",
        "          " + _ruler(days) + "   per-season days >= 1/10",
    ]
    for season, row, count in zip(seasons, matrix, per_season):
        lines.append(f"    {season}  " + "".join(_glyph(v) for v in row)
                     + ("   —" if np.isnan(count) else f"   {count:.0f}"))
    lines += [
        "",
        "    cross-season median CT   " + "".join(_glyph(v) for v in median_series),
        "    cross-season mean CT     " + "".join(_glyph(v) for v in mean_series),
        f"    mediantt = days the median series holds >= 1/10 : {a['mediantt']:g} d",
        f"    meantt   = days the mean series holds >= 1/10   : {a['meantt']:g} d",
        f"    ttmedian = median of the per-season counts      : {a['ttmedian']:g} d",
        "",
    ]
    return lines


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Stamped, not overwritten: a run's report is only readable against the code that
    # produced it, so re-running after a change must not erase what it is compared to.
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    rng = np.random.default_rng(0)

    ctx = context(BASELINE)
    base = product(ctx)
    candidates = {c: product(context(c)) for c in CANDIDATES}
    deltas = {c: delta(base, p) for c, p in candidates.items()}
    tier = ctx.region.tiers[-1]
    groups = [g for c, d in deltas.items() for g in tail_patches(c, d, tier.wet_mask)]

    groups_png(deltas, groups, OUTPUT_DIR / f"{stamp}_{METRIC}_tail_patches.png")

    df = filter_admissible_days(_fetch(ctx).prepare(ctx.metric.conversion))
    seasons = sorted(int(s) for s in df["season"].unique())

    columns = {g.label: wet_columns(g, tier, rng) for g in groups}
    offsets = np.cumsum([0] + [len(c) for c in columns.values()])
    cube, days = ct_cube(df, tier, np.concatenate(list(columns.values())))

    lines = [f"probe 034 — {stamp} — CT configurations of the coherent patches "
             f"at the delta-lattice tails",
             f"{METRIC} | {REGION} | {SOURCE} | {PERIOD} | tier {TIER} | "
             f"baseline {BASELINE}", ""]
    for g, lo, hi in zip(groups, offsets, offsets[1:]):
        cases_png(cube[:, :, lo], days, g,
                  OUTPUT_DIR / f"{stamp}_{METRIC}_cases_{g.label.replace(' ', '')}.png")
        lines += group_report(
            g, cube[:, :, lo:hi], days, seasons, step_days=ctx.source.step_days,
            base=base.values.ravel()[g.cell],
            cand=candidates[g.candidate].values.ravel()[g.cell])

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}_{METRIC}_configurations.txt").write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
