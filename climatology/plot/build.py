"""Plot orchestration: one figure, resolved from slugs and built out of the archive.

The DAG mirrors ``climatology/pipeline.py``: a frozen context resolved first, one guard
stage before any raster is read, then the work.

    build() -> _resolve -> _validate -> _fetch -> _render -> PlotProduct
               PlotContext  manifests   rasters   dispatch

``_validate`` reads each run's ``.json`` manifest and rejects both an incoherent plot
configuration and an incoherent archive; ``_fetch`` then loads only the ``.npz`` files those
manifests already located. Splitting it that way keeps the cheap check ahead of the megabytes,
and leaves each stage one concern: locate-and-check, load, draw.

Two callers, one path — the CLI here, and ``pipeline`` after it has emitted a run's archive.
Neither hands in rasters: a figure is always built from what is on disk, so a plot is
reproducible from the archive alone.

Usage:
    python -m climatology.plot.build METRIC --region R --period P --source S --reduction X

A run is identified by region, metric, period, source and reduction. Region is pinned — panels
must overlay on one grid — so the figure branches on the other three: pass ``a:b:c`` to any
of ``--period``, ``--source``, ``--reduction`` and it becomes the axis of comparison, with the
pinned coordinates broadcast across it. Run the sweep first; every run named must already
be archived.

    # one run, one map: the same figure the pipeline emits per run
    python -m climatology.plot.build freeze_up_date --region manicouagan \\
        --period 2011-2020 --source sgrda --layout single --no-distribution \\
        --out freeze_up_manicouagan_2011-2020.png

    # every period side by side on one colour scale (source co-varies, so both branch)
    python -m climatology.plot.build freeze_up_date --region manicouagan \\
        --period 1971-2000:1981-2010:1991-2020:2011-2020 \\
        --source sgrdr:sgrdr:sgrdr:sgrda \\
        --out freeze_up_manicouagan_periods.png

    # signed change, SGRDR against SGRDR — chart type held fixed, since data
    # reliability is chart-type dependent (Angela Cheng/CIS, pers. comm. 2026).
    # One comparison is one panel, hence `single`.
    python -m climatology.plot.build breakup_date --region manicouagan \\
        --type delta --layout single --source sgrdr \\
        --period 1981-2010:2011-2020 \\
        --out breakup_manicouagan_delta.png

    # baseline / candidate / change, one portrait
    python -m climatology.plot.build breakup_date --region manicouagan \\
        --type delta --layout portrait --no-distribution --source sgrdr \\
        --period 1981-2010:2011-2020 \\
        --out breakup_manicouagan_portrait.png

    # branch on reduction instead: same region, period and source, two estimators.
    # "median date of break-up" against "date the median CT crosses 4/10" — the delta
    # panel maps where the two orders disagree, in days.
    python -m climatology.plot.build breakup_date --region manicouagan \\
        --type delta --layout portrait \\
        --period 1991-2020 --source sgrdr --reduction mediantt:ttmedian \\
        --out breakup_manicouagan_reduction.png
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from climatology.plot.render import (
    DeltaPanel,
    MetricPanel,
    plot_metric,
    plot_metric_panels,
    plot_source_portrait,
)
from climatology.core.context import RunContext
from climatology.core.metrics import Metric
from climatology.core.reduction.spatial import RasterLayer
from climatology.core.reduction.temporal import MEDIAN_THEN_THRESHOLD, Reduction
from climatology.core.regions import Region
from climatology.core.export import load_archived
from climatology.services.sources import ChartSource
from climatology.core.context import Result

if TYPE_CHECKING:
    from matplotlib.figure import Figure

log = logging.getLogger(__name__)

RAW, DELTA = "raw", "delta"
SINGLE, MULTI, PORTRAIT = "single", "multi", "portrait"

# The product coordinates a figure can branch on, in title order. Region is the fourth and
# is pinned: panels that do not share a grid cannot overlay, let alone be differenced.
COORDS = ("period", "source", "reduction")

GRID_MATCH_CELLS = 0.01   # bounds within 1/100 of a cell are the same grid


# --- context ----------------------------------------------------------------

@dataclass(frozen=True)
class PlotContext:
    """How to lay out one figure, over the runs it draws.

    A ``RunContext`` already *is* a figure's unit of comparison — it names the region, metric,
    period, source and reduction one archived product was written under. So this holds the runs
    and nothing but the presentation: region and metric are read off the first run, since region
    is pinned across the figure and the metric is bound to that run's reduction.
    """

    runs: tuple[RunContext, ...]
    type: str = RAW                 # raw | delta
    layout: str = MULTI             # single | multi | portrait
    distribution: bool = True

    def assert_shared_regions(ctx: PlotContext) -> None:
        """Region is pinned across the figure — panels that do not share a grid cannot be
        overlaid on one extent, let alone differenced cell by cell."""
        slugs = sorted({run.region.slug for run in ctx.runs})
        if len(slugs) > 1:
            raise ValueError(
                f"A figure draws one region; got {slugs}. Pin --region and branch on "
                f"{', '.join(COORDS)} instead.")

    def assert_shared_metrics(ctx: PlotContext) -> None:
        """One metric across the figure — the reduction may branch, the quantity may not.

        ``ctx.metric`` carries the figure's title, unit and colour scale and is read off the
        first run, so a second quantity would be drawn under the first one's label.
        """
        slugs = sorted({run.metric.slug for run in ctx.runs})
        if len(slugs) > 1:
            raise ValueError(
                f"A figure draws one metric; got {slugs}. One metric per figure — "
                "branch on reduction to compare estimators of the same quantity.")

    @property
    def region(self) -> Region:
        return self.runs[0].region

    @property
    def metric(self) -> Metric:
        return self.runs[0].metric

    @property
    def axes(self) -> tuple[str, ...]:
        """The coordinates that actually differ across the runs — what a panel title must
        name, and by complement what the subtitle can state once for the whole figure."""
        return tuple(name for name in COORDS
                     if len({_coords(run)[name] for run in self.runs}) > 1)

    @property
    def key(self) -> tuple[str, str, bool]:
        """The renderer this configuration selects."""
        return (self.type, self.layout, self.distribution)


@dataclass(frozen=True)
class PlotProduct:
    """A rendered figure and how it must be written.

    ``tight`` is a property of the layout, not of the caller: a tight bbox crops each side to
    its own artists, which pulls a centred suptitle off-centre on the multi-map layouts.
    """

    figure: Figure
    tight: bool


# --- naming -----------------------------------------------------------------
# Which coordinates distinguish a panel depends on which one the figure branched on, so the
# titles are decided here and handed to the renderers as data. Varying coordinates title the
# panels; pinned ones are stated once, in the subtitle.

def _coords(run: RunContext) -> dict[str, str]:
    """A run's branchable coordinates, as the slugs the CLI names them by."""
    return {"period": run.period.slug, "source": run.source.slug,
            "reduction": run.metric.reduction_slug}


def _label(run: RunContext) -> str:
    """One run named in a log line or an error message."""
    text = _coords(run)
    return f"{text['period']} {text['source'].upper()} {text['reduction']}"


def _coord_text(run: RunContext) -> dict[str, str]:
    """Each coordinate as it should read, already cased — the source and reduction are slugs
    and stay lowercase, so the assembled title must never be re-cased as a whole."""
    return {**_coords(run), "period": f"Winters {run.period.slug}"}


def _panel_title(ctx: PlotContext, run: RunContext) -> str:
    """Panel heading: the coordinates that distinguish this run from the figure's others."""
    named = ctx.axes or ("period", "source")   # a lone run still says what it is
    text = _coord_text(run)
    # "·", not an em dash: a delta title joins two of these with "−", and the two dashes
    # are indistinguishable at title size.
    return " · ".join(text[name] for name in COORDS if name in named)


def _subtitle(ctx: PlotContext) -> str:
    """Figure subtitle: the coordinates every panel shares (the varying ones title the panels)."""
    text = _coord_text(ctx.runs[0])
    return " · ".join(text[name] for name in COORDS if name not in ctx.axes)


# --- renderer registry ------------------------------------------------------
# One row per (type, layout, distribution) the archive can actually produce. A combination
# absent here is not silently approximated — `_validate` names it and the available ones.

@dataclass(frozen=True)
class Renderer:
    """How one configuration turns fetched panels into a figure."""

    draw: object                    # (ctx, panels) -> Figure
    n_runs: int | None              # required run count; None = any
    tight: bool = False


def _draw_single(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """One run, one map, no distribution — the per-run product the pipeline emits."""
    panel = panels[0]
    return plot_metric([(l.values, l.bounds) for l in panel.layers],
                       metric=ctx.metric, region_display=ctx.region.display,
                       res_label=_res_label(panel), period_slug=panel.period,
                       source_label=panel.source.display_label)


def _draw_multi(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Every run side by side on one colour scale and one extent."""
    return plot_metric_panels(panels, metric=ctx.metric,
                              region_display=ctx.region.display,
                              res_label=_res_label(panels[0]))


def _draw_portrait(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Baseline and candidate over their change — two runs, two scales, one figure."""
    base, cand = panels
    return plot_source_portrait(base, cand, _delta_panel(base, cand),
                                metric=ctx.metric,
                                region_display=ctx.region.display,
                                res_label=_res_label(base),
                                subtitle=_subtitle(ctx),
                                distribution=ctx.distribution)


RENDERERS: dict[tuple[str, str, bool], Renderer] = {
    (RAW,   SINGLE,   False): Renderer(_draw_single,   n_runs=1,    tight=True),
    (RAW,   MULTI,    True):  Renderer(_draw_multi,    n_runs=None),
    (DELTA, PORTRAIT, False): Renderer(_draw_portrait, n_runs=2),
    (DELTA, PORTRAIT, True):  Renderer(_draw_portrait, n_runs=2),
}


def _res_label(panel: MetricPanel) -> str:
    return " / ".join(f"{int(round(layer.res_m))} m" for layer in panel.layers)


def _delta_panel(base: MetricPanel, cand: MetricPanel) -> DeltaPanel:
    """Candidate − baseline per tier, on the shared region+tier grid (direct subtraction)."""
    return DeltaPanel(
        title=f"{cand.title} − {base.title}",
        layers=[RasterLayer(values=c.values - b.values, bounds=c.bounds, res_m=c.res_m)
                for b, c in zip(base.layers, cand.layers)],
        reductions=(base.reduction, cand.reduction),
    )


# --- stages -----------------------------------------------------------------

def _resolve(runs: tuple[RunContext, ...], *,
             type: str, layout: str, distribution: bool) -> PlotContext:
    """Bind the runs to a layout, and announce the figure (mirrors ``pipeline._resolve``).

    ``ctx.metric`` is the first run's — so it is bound to that run's reduction. Everything the
    metric is asked for downstream — its title, its tick formatter, whether it counts steps —
    is order-independent; the order-dependent labels are taken per panel, from that panel's
    own reduction.
    """
    ctx = PlotContext(runs=runs, type=type, layout=layout, distribution=distribution)
    log.info("Figure: %s %s/%s | Metric: %s | Region: %s | Branching on: %s | Runs: %s",
             ctx.type, ctx.layout, "dist" if ctx.distribution else "nodist",
             ctx.metric.slug, ctx.region.slug, ", ".join(ctx.axes) or "nothing",
             ", ".join(_label(run) for run in ctx.runs))
    return ctx

def _validate(ctx: PlotContext) -> None:
    """Reject an incoherent figure before a single raster is read.

    Two halves, both answerable without loading anything: the *configuration*, from the
    context alone, and the *archive*, from the ``.json`` manifests ``find_archived`` already
    reads to select a product. Returns the refs per run, coarse tier first, so ``_fetch``
    loads exactly what was approved here and nothing re-decides.
    """
    ctx.assert_shared_regions()
    ctx.assert_shared_metrics()


def _fetch(ctx: PlotContext) -> list[tuple[RasterLayer, ...]]:
    """Load each run's archived tiers, coarse first; append the per-tier difference for a delta."""
    archives = [load_archived(run) for run in ctx.runs]
    if ctx.type == DELTA:
        base, cand = archives[0], archives[1]
        archives.append(tuple(RasterLayer(c.values - b.values, c.bounds, c.res_m)
                              for b, c in zip(base, cand)))
    log.info("Loaded %d raster(s).", sum(len(a) for a in archives))
    return archives


def _render(ctx: PlotContext, results: list[Result]) -> PlotProduct:
    """Draw the figure this configuration selects — the one dispatch seam over the renderers."""
    renderer = RENDERERS[ctx.key]
    return PlotProduct(figure=renderer.draw(ctx, panels), tight=renderer.tight)


def build_figure(runs: tuple[RunContext, ...], *,
          type: str = RAW, layout: str = MULTI,
          distribution: bool = True) -> PlotProduct:
    """Build one figure from the archive; the caller writes it via ``export.save_figure``."""
    ctx = _resolve(runs, type=type, layout=layout, distribution=distribution)
    _validate(ctx)
    layers = _fetch(ctx)
    panels
    return _render(ctx, results)


# --- CLI --------------------------------------------------------------------

def _axis(name: str, choices: tuple[str, ...] | None = None):
    #arg parse concern
    """An argparse type for one run coordinate as a branch: ``a`` or ``a:b:c``."""
    def parse(spec: str) -> tuple[str, ...]:
        values = tuple(spec.split(":"))
        if choices is not None:
            bad = [v for v in values if v not in choices]
            if bad:
                raise argparse.ArgumentTypeError(
                    f"Unknown {name} {bad}; choose from {', '.join(sorted(choices))}.")
        return values
    return parse


def _assert_uniform(parser: argparse.ArgumentParser, axes: dict[str, tuple[str, ...]]) -> None:
    """Reject ragged branches — one branch length is allowed beside the pinned length 1.

    A coordinate is either held across the figure or carries one value per panel.
    ``--reduction a:b`` against ``--period x:y:z`` is a mistake, not a request for the
    six-panel cross product.
    """
    n = max(len(values) for values in axes.values())
    ragged = {k: v for k, v in axes.items() if len(v) not in (1, n)}
    if ragged:
        parser.error(
            f"Coordinate axes must be length 1 or {n}; got "
            + ", ".join(f"--{k} with {len(v)}" for k, v in ragged.items())
            + ". Pin a coordinate to one value, or give it one value per panel.")


def _broadcast(region: str, metric: str, periods: tuple[str, ...], sources: tuple[str, ...],
               reductions: tuple[str, ...]) -> tuple[RunContext, ...]:
    # resolve concern
    """Zip the coordinate axes into runs, broadcasting the pinned (length-1) ones."""
    axes = {"period": periods, "source": sources, "reduction": reductions}
    n = max(len(values) for values in axes.values())
    picked = ({k: v[0] if len(v) == 1 else v[i] for k, v in axes.items()} for i in range(n))
    return tuple(RunContext.build(region, metric, p["period"], p["source"], p["reduction"])
                 for p in picked)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", choices=Metric.slugs(), metavar="METRIC")
    p.add_argument("--region", choices=Region.slugs(), required=True, metavar="REGION",
                   help="Pinned across the figure — panels must overlay on one grid.")
    p.add_argument("--period", type=_axis("period"), default=("2011-2020",),
                   metavar="YYYY-YYYY[:...]",
                   help="Climatology period(s) in winters; colon-separated to branch.")
    p.add_argument("--source", type=_axis("source", tuple(ChartSource.slugs())),
                   default=("sgrda",), metavar="SOURCE[:...]",
                   help=f"Chart table(s); colon-separated to branch. "
                        f"Choices: {', '.join(ChartSource.slugs())}.")
    p.add_argument("--reduction", type=_axis("reduction", tuple(Reduction.slugs())),
                   default=(MEDIAN_THEN_THRESHOLD.slug,), metavar="REDUCTION[:...]",
                   help=f"Reduction order(s) whose archives to read; colon-separated to "
                        f"branch. Choices: {', '.join(Reduction.slugs())}.")
    p.add_argument("--type", choices=(RAW, DELTA), default=RAW,
                   help="Absolute values, or the signed change between products.")
    p.add_argument("--layout", choices=(SINGLE, MULTI, PORTRAIT), default=MULTI,
                   help="One map, a panel grid, or a baseline/candidate/change portrait.")
    p.add_argument("--no-distribution", action="store_false", dest="distribution",
                   help="Drop the area-weighted value distribution beside each map.")
    p.add_argument("--out", type=Path, required=True, metavar="PNG",
                   help="Where to write the figure.")
    args = p.parse_args()
    _assert_uniform(p, {"period": args.period, "source": args.source,
                        "reduction": args.reduction})
    return args


def main() -> None:
    from dotenv import load_dotenv

    from climatology.core.export import save_figure

    # Only on the CLI path: MAPBOX_TOKEN reaches `plot.basemap` through the environment, and
    # importing this module (as `pipeline` does) must not have the side effect of setting it.
    # Every other entry point — main, sweep — bootstraps the same way.
    load_dotenv(Path(__file__).parents[2] / ".env")

    logging.basicConfig(level=logging.INFO, datefmt="%H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    runs = _broadcast(args.region, args.metric, args.period, args.source, args.reduction)
    product = build_figure(runs, type=args.type,
                    layout=args.layout, distribution=args.distribution)
    save_figure(product.figure, args.out, tight=product.tight)


if __name__ == "__main__":
    main()
