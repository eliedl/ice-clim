"""Figure colour vocabulary: the dark theme, the named palettes, and the colour scales built from them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize

from climatology.plot.labels import DELTA, RASTER, RAW, SERIES
from climatology.services.calendar import day_of_season, month_start
from climatology.utils.arithmetics import percentile_range

if TYPE_CHECKING:
    from climatology.core.reduction.spatial import RasterLayer
    from climatology.core.reduction.temporal import SeriesLayer
    from climatology.plot.build import PlotContext

# Dark "Mapbox-style" theme. Ocean = axes background (shows through NaN /
# ice-free cells); land polygons are painted on top so they cover dry cells only.
DARK_OCEAN = "#0b0f14"
DARK_LAND  = "#1c2128"
DARK_COAST = "#3a4350"
DARK_FG    = "#dfe3e8"
DARK_MUTED = "#7a828c"
DARK_LINE  = "#3a3f47"

PALETTES: dict[str, list[tuple[float, str]]] = {
    # 7-stop cool-to-warm sequential ramp (teal -> indigo -> plum -> ember -> red).
    RAW: [
        (0.0,     "#7dc6d5"),
        (1 / 6,   "#6576bb"),
        (2 / 6,   "#5b389a"),
        (3 / 6,   "#a05b55"),
        (4 / 6,   "#e17117"),
        (5 / 6,   "#ed5009"),
        (1.0,     "#f63601"),
    ],
    DELTA: [
        (0.0, "#2166ac"),
        (0.25, "#67a9cf"),
        (0.5, "#f7f7f7"),
        (0.75, "#ef8a62"),
        (1.0, "#b2182b"),
    ],
}

# A sibling of PALETTES, not a row in it: those are ramps, read by position, and a series maps
# nothing from a value — it needs one colour per mark. Keyed by ``SeriesPalette`` field, so the
# two stay in step and a mark added there fails loudly here rather than drawing uncoloured.
SERIES_COLORS: dict[str, str] = {
    "points":     "#a05422",
    "mean":       "#ded9d2",
    "inner_band": "#1b4a69",
    "outer_band": "#95bbd0",
}

def style_axes(ax) -> None:
    # Render concern
    """Dark-theme the ticks and spines."""
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)


def style_colorbar(cbar, *, label: str, tick_values: list[float],
                   tick_labels: list[str]) -> None:
    # Render concern
    """Dark-theme a colourbar and apply the metric's tick formatting."""
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)
    cbar.set_label(label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)


def build_cmap(
    palette: str,
    vmin: float,
    vmax: float,
) -> tuple[Colormap, Normalize]:
    """Build a ``(cmap, norm)`` pair anchored to ``[vmin, vmax]``."""
    stops = PALETTES[palette] if isinstance(palette, str) else palette
    positions = [p for p, _ in stops]
    colors = [mcolors.to_rgba(c) for _, c in stops]

    cmap = LinearSegmentedColormap.from_list(
        "custom", list(zip(positions, colors)), N=1024,
    )

    return cmap, Normalize(vmin=vmin, vmax=vmax, clip=False)


# --- value-range scales -----------------------------------------------------
# Each carries the tick *positions* only; formatting them into labels is the
# caller's business, since what a value means (a date, a day count, a signed
# change) is not something a palette knows.

@dataclass(frozen=True)
class RasterScale:
    """One map panel's colour mapping: the ramp, the range it is anchored on, and its tick positions."""

    cmap: Colormap
    norm: Normalize
    ticks: list[float]


@dataclass(frozen=True)
class SeriesPalette:
    """What a series panel is drawn with, and the axis it is read on.

    Carries ``ticks`` for the same reason ``RasterScale`` does: the tick *positions* are
    resolved here, the text ``Label.format_ticks`` puts on them is resolved in ``labels``.
    Neither half means anything without the other, which is why paired stages produce them.
    """

    points: str          # the per-season values
    mean: str            # the across-season daily mean
    inner_band: str      # mean ± half a standard deviation
    outer_band: str      # mean ± a standard deviation
    days: np.ndarray     # x position of every column, in the ordinals ``ticks`` is measured in
    ticks: list[float]   # month starts — the positions ``format_ticks`` labels


def _ticks_values(vmin: float, vmax: float, type: str) -> list[float]:
    """Six ticks across a value range; five across a delta's ±span, dropped to three when the
    half-steps would not survive integer rounding.

    A day-count delta labels its ticks as integers, so a half-step that rounds onto either
    its end tick or the centre renders as a duplicate label — the latter is the
    ``DELTA_FALLBACK_VABS`` floor, reached whenever the delta is ~flat everywhere.
    """
    if type != DELTA:
        return list(np.linspace(vmin, vmax, 6))
    if round(vmax / 2) in (round(vmax), 0):
        return [vmin, 0.0, vmax]
    return list(np.linspace(vmin, vmax, 5))


def _scale(values: np.ndarray, type: str) -> RasterScale:
    """One map panel's colour scale: sequential over the value range, or diverging and symmetric
    about zero for a delta, so a colour's direction reads as the sign of the change."""
    if type == DELTA:
        _, vmax = percentile_range(np.abs(values))  # keep delta values up to the 99th percentile
        vmin = -vmax
    else:
        vmin, vmax = percentile_range(values, low=1, high=100)  # drops near-coast extremas
    cmap, norm = build_cmap(type, vmin=vmin, vmax=vmax)
    return RasterScale(cmap, norm, _ticks_values(vmin, vmax, type))


# --- the series' day axis ----------------------------------------------------
# A series panel is anchored on days rather than on a value range, so its axis is resolved
# here beside the colour scales: same concern — what the panel's positions mean — read off
# the archive rather than off the data drawn on it.

# The one week a 52-week lattice stretches to absorb the 365th day: CIS weekly charts run
# Jan 1 + 7k up to Nov 26, then resume on Dec 4 rather than Dec 3. Every ordinal past it
# therefore sits one day later than a constant step would place it.
WEEK_RESET_DAY = day_of_season("11-26")


def series_days(layer: SeriesLayer) -> np.ndarray:
    # Labels concern
    """A series' column axis: the day-of-season ordinals its archived extent spans."""
    
    days = layer.first_day + layer.day_step * np.arange(layer.values.shape[1])
    if days[-1] == layer.last_day:
        return days                                   # constant step throughout (daily charts)
    if days[-1] + 1 == layer.last_day:
        return days + (days > WEEK_RESET_DAY)         # 52-week lattice, one 8-day week
    raise ValueError(
        f"Series day axis does not reach its recorded extent: {layer.first_day} + "
        f"{layer.day_step} × {layer.values.shape[1]} columns ends on day {days[-1]}, but the "
        f"manifest records {layer.last_day}.")


# --- scale policy: which panels pool into one scale --------------------------
# Two levels, because two questions. The kind decides *which family* a panel is resolved into —
# a colour scale for a map, a set of marks for a series — and only within the raster family does
# the figure's type matter: a delta's trailing panel is a difference and cannot share a
# sequential ramp with the values it was computed from.

def _pool(stacks: list[tuple[RasterLayer, ...]]) -> np.ndarray:
    """Every cell of every tier of every stack — what a shared scale is anchored on.

    Pooling across tiers as well as panels is deliberate: the fine tier's coastal cells are
    exactly the ones a coarse-only range would drop off the scale.
    """
    return np.concatenate([layer.values.ravel() for stack in stacks for layer in stack])


def _one_sequential(layers: list[tuple[RasterLayer, ...]]) -> list[RasterScale]:
    """One sequential scale over every panel: a colour means the same value figure-wide."""
    return [_scale(_pool(layers), RAW)] * len(layers)


def _sequential_plus_delta(layers: list[tuple[RasterLayer, ...]]) -> list[RasterScale]:
    """Value panels on one shared sequential scale; the trailing difference on its own diverging one.

    Pooling baseline and candidate together is the point of the figure: the shift between
    them then reads as a colour change, not as two independently stretched ramps.
    """
    *values, delta = layers
    return [_scale(_pool(values), RAW)] * len(values) + [_scale(_pool([delta]), DELTA)]


_RASTER_SCALES = {RAW: _one_sequential, DELTA: _sequential_plus_delta}


def _raster_scales(ctx: PlotContext,
                   layers: list[tuple[RasterLayer, ...]]) -> list[RasterScale]:
    """One colour scale per map panel, under the pooling policy the figure's type calls for."""
    return _RASTER_SCALES[ctx.type](layers)


def series_months(layer: SeriesLayer) -> list[float]:
    """Day-of-season of the first of each month the series actually carries ice in.

    Filtered, not merely derived. The weekly charts run year-round, so a concentration series
    holds a five-month summer plateau of exact zeros; ticking those months would spend half the
    axis labelling an empty stretch. The set collapses the four-or-five columns that share a
    month — ``series_days`` is strictly increasing, so nothing upstream needs deduplicating.
    """
    days = series_days(layer)
    carries = layer.values.max(axis=0) > 0.0
    return sorted({month_start(day) for day, keep in zip(days, carries) if keep})


def _series_scales(ctx: PlotContext,
                   layers: list[tuple[SeriesLayer, ...]]) -> list[SeriesPalette]:
    """One palette per series panel, every panel read on the same months.

    The ticks pool across panels for the reason ``_one_sequential``'s scale does — a position
    has to mean the same month everywhere — while ``days`` stays per panel, since two sources
    chart on different lattices and one shared axis would misplace the finer one.
    """
    ticks = sorted({month for stack in layers for month in series_months(stack[0])})
    return [SeriesPalette(**SERIES_COLORS, days=series_days(stack[0]), ticks=ticks)
            for stack in layers]


_SCALES = {RASTER: _raster_scales, SERIES: _series_scales}


def style(ctx: PlotContext,
          layers: list[tuple]) -> list[RasterScale] | list[SeriesPalette]:
    """One scale or palette per layer stack, index-aligned — a delta figure's last stack is the difference.

    Panels sharing a scale share one frozen instance, so "same colour, same value" holds by
    identity rather than by two computations that happen to agree.
    """
    return _SCALES[ctx.kind](ctx, layers)
