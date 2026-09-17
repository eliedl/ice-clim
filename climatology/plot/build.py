"""Plot orchestration: one figure, resolved from slugs and built out of the archive.

The DAG mirrors ``climatology/pipeline.py``: a frozen context resolved first, one guard
stage before any raster is read, then the work.

    build() -> _resolve -> _validate -> _fetch -> label -> style -> layout -> render
               PlotContext  guards      rasters   text    colour   axes      Figure

``_validate`` rejects an incoherent configuration before a raster is read; ``_fetch`` then
loads the archive and *is* what fixes the panel list — the three stages after it each resolve
one concern over that list and return it index-aligned, so a panel's place in the figure is
its place in ``rasters``.

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

The figure's shape is not configured, it is *derived*: ``--type raw`` draws one panel per run,
``--type delta`` draws the two runs it differences and their change. A partial final row is
centred under the rows above it.

    # one run, one map: the same figure the pipeline emits per run
    python -m climatology.plot.build freeze_up_date --region manicouagan \\
        --period 2011-2020 --source sgrda \\
        --out freeze_up_manicouagan_2011-2020.png

    # every period side by side on one colour scale (source co-varies, so both branch)
    python -m climatology.plot.build freeze_up_date --region manicouagan \\
        --period 1971-2000:1981-2010:1991-2020:2011-2020 \\
        --source sgrdr:sgrdr:sgrdr:sgrda \\
        --out freeze_up_manicouagan_periods.png

    # baseline, candidate and their signed change — SGRDR against SGRDR, chart type held
    # fixed since data reliability is chart-type dependent (Angela Cheng/CIS, pers. comm. 2026)
    python -m climatology.plot.build breakup_date --region manicouagan \\
        --type delta --source sgrdr \\
        --period 1981-2010:2011-2020 \\
        --out breakup_manicouagan_delta.png

    # branch on reduction instead: same region, period and source, two estimators.
    # "median date of break-up" against "date the median CT crosses 4/10" — the change
    # panel maps where the two orders disagree, in days.
    python -m climatology.plot.build breakup_date --region manicouagan \\
        --type delta \\
        --period 1991-2020 --source sgrdr --reduction mediantt:ttmedian \\
        --out breakup_manicouagan_reduction.png
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from climatology.plot.render import render
from climatology.plot.colors import style
from climatology.plot.labels import COORDS, DELTA, RAW, branch, label, run_label
from climatology.plot.layout import layout
from climatology.core.context import RunContext
from climatology.core.metrics import Metric
from climatology.core.reduction.spatial import RasterLayer
from climatology.core.reduction.temporal import MEDIAN_THEN_THRESHOLD, Reduction
from climatology.core.regions import Region
from climatology.core.export import load_archived
from climatology.services.sources import ChartSource

if TYPE_CHECKING:
    from matplotlib.figure import Figure

log = logging.getLogger(__name__)

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


# --- stages -----------------------------------------------------------------

def _resolve(runs: tuple[RunContext, ...], *, type: str) -> PlotContext:
    """Bind the runs to a figure type, and announce it (mirrors ``pipeline._resolve``).

    ``ctx.metric`` is the first run's — so it is bound to that run's reduction. Everything the
    metric is asked for downstream — its title, its tick formatter, whether it counts steps —
    is order-independent; the order-dependent labels are taken per panel, from that panel's
    own reduction.
    """
    ctx = PlotContext(runs=runs, type=type)
    log.info("Figure: %s | Metric: %s | Region: %s | Branching on: %s | Runs: %s",
             ctx.type, ctx.metric.slug, ctx.region.slug,
             ", ".join(branch(runs)) or "nothing",
             ", ".join(run_label(run) for run in ctx.runs))
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
    rasters = [load_archived(run) for run in ctx.runs]
    if ctx.type == DELTA:
        base, cand = rasters[0], rasters[1]
        rasters.append(tuple(RasterLayer(c.values - b.values, c.bounds, c.res_m)
                              for b, c in zip(base, cand)))
    log.info("Loaded %d raster(s).", sum(len(a) for a in rasters))
    return rasters


def build_figure(runs: tuple[RunContext, ...], *, type: str = RAW) -> Figure:
    """Build one figure from the archive; the caller writes it via ``export.save_figure``.

    The four stages after the guard each resolve one concern over the same panel list, and
    each returns a list indexed by panel: the rasters, their text, their colour, and the axes
    they draw into. ``render`` walks the four together, so panel order *is* raster order.
    """
    ctx = _resolve(runs, type=type)
    _validate(ctx)
    rasters = _fetch(ctx)
    labels = label(ctx, rasters)
    scales = style(ctx, rasters)
    panels = layout(ctx, rasters)
    return render(rasters, labels, scales, panels)



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
    figure = build_figure(runs, type=args.type)
    save_figure(figure, args.out)


if __name__ == "__main__":
    main()
