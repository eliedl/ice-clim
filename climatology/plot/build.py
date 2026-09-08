"""Plot orchestration: one figure, resolved from slugs and built out of the archive.

The DAG mirrors ``climatology/pipeline.py``: a frozen context resolved first, one guard
stage before any raster is read, then the work.

    build() -> _resolve -> _validate -> _fetch -> _render -> PlotProduct
               PlotContext  manifests   rasters   dispatch

``_validate`` reads each product's ``.json`` manifest and rejects both an incoherent plot
configuration and an incoherent archive; ``_fetch`` then loads only the ``.npz`` files those
manifests already located. Splitting it that way keeps the cheap check ahead of the megabytes,
and leaves each stage one concern: locate-and-check, load, draw.

Two callers, one path — the CLI here, and ``pipeline`` after it has emitted a run's archive.
Neither hands in rasters: a figure is always built from what is on disk, so a plot is
reproducible from the archive alone.

Usage:
    python -m climatology.plot.build METRIC REGION --era PERIOD:SOURCE ... --out FIG.png

``--era`` is repeatable and *ordered*; a delta differences consecutive pairs. Run the sweep
first — every era named must already be archived under the requested reduction.

    # one era, one map: the same figure the pipeline emits per run
    python -m climatology.plot.build freeze_up_date manicouagan \\
        --era 2011-2020:sgrda --layout single --no-distribution \\
        --out freeze_up_manicouagan_2011-2020.png

    # every era side by side on one colour scale (per-era composite)
    python -m climatology.plot.build freeze_up_date manicouagan \\
        --era 1971-2000:sgrdr --era 1981-2010:sgrdr \\
        --era 1991-2020:sgrdr --era 2011-2020:sgrda \\
        --out freeze_up_manicouagan_eras.png

    # signed change, SGRDR against SGRDR — chart type held fixed, since data
    # reliability is chart-type dependent (Angela Cheng/CIS, pers. comm. 2026).
    # One comparison is one panel, hence `single`.
    python -m climatology.plot.build breakup_date manicouagan \\
        --type delta --layout single \\
        --era 1981-2010:sgrdr --era 2011-2020:sgrdr \\
        --out breakup_manicouagan_delta.png

    # baseline / candidate / change, one portrait
    python -m climatology.plot.build breakup_date manicouagan \\
        --type delta --layout portrait --no-distribution \\
        --era 1981-2010:sgrdr --era 2011-2020:sgrdr \\
        --out breakup_manicouagan_portrait.png
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
    plot_delta_panels,
    plot_metric,
    plot_metric_panels,
    plot_source_portrait,
)
from climatology.plot.validate import assert_comparable, assert_one_reduction
from climatology.processing.metrics import METRICS
from climatology.processing.reduction.spatial import RasterLayer
from climatology.processing.reduction.temporal import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.processing.regions import REGIONS, RegionSpec
from climatology.services.export import find_archived
from climatology.services.sources import CHART_TABLES

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from climatology.processing.metrics import MetricSpec
    from climatology.services.sources import ChartTable

log = logging.getLogger(__name__)

RAW, DELTA = "raw", "delta"
SINGLE, MULTI, PORTRAIT = "single", "multi", "portrait"

GRID_MATCH_CELLS = 0.01   # bounds within 1/100 of a cell are the same grid


# --- context ----------------------------------------------------------------

@dataclass(frozen=True)
class Era:
    """One archived product's period/source coordinates — a figure's unit of comparison."""

    period: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.period} {self.source.upper()}"


@dataclass(frozen=True)
class PlotContext:
    """Resolved, immutable identity of one figure: what to draw, and how to lay it out.

    ``type``/``layout``/``distribution`` are the presentation axes the CLI sets; the rest
    names the archived products the figure is built from. A delta reads its eras pairwise
    (candidate − baseline), so ``eras`` is ordered and its length is layout-dependent —
    ``_validate`` is what holds that rule.
    """

    region: RegionSpec
    metric: MetricSpec              # carries the reduction order
    eras: tuple[Era, ...]
    type: str = RAW                 # raw | delta
    layout: str = MULTI             # single | multi | portrait
    distribution: bool = True

    @property
    def tiers(self) -> list[str]:
        return [tier.level for tier in self.region.tiers]

    @property
    def reduction(self) -> str:
        return self.metric.reduction.slug

    @property
    def key(self) -> tuple[str, str, bool]:
        """The renderer this configuration selects."""
        return (self.type, self.layout, self.distribution)


@dataclass(frozen=True)
class ArchiveRef:
    """One archived product located and described, before its raster is read.

    Carries ``source`` and ``reduction`` so ``plot.validate``'s assertions — which only ever
    read those two — can run on manifests, ahead of the load.
    """

    era: Era
    tier: str
    npz: Path
    manifest: dict

    @property
    def source(self) -> ChartTable:
        return CHART_TABLES[self.era.source]

    @property
    def reduction(self) -> str:
        return self.manifest["reduction"]

    @property
    def bounds(self) -> tuple[float, ...]:
        return tuple(self.manifest["bounds"])

    @property
    def grid_shape(self) -> tuple[int, int]:
        return tuple(self.manifest["grid_shape"])

    @property
    def res_m(self) -> float:
        return float(self.manifest["grid_res_m"])


@dataclass(frozen=True)
class PlotProduct:
    """A rendered figure and how it must be written.

    ``tight`` is a property of the layout, not of the caller: a tight bbox crops each side to
    its own artists, which pulls a centred suptitle off-centre on the multi-map layouts.
    """

    figure: Figure
    tight: bool


# --- renderer registry ------------------------------------------------------
# One row per (type, layout, distribution) the archive can actually produce. A combination
# absent here is not silently approximated — `_validate` names it and the available ones.

@dataclass(frozen=True)
class Renderer:
    """How one configuration turns fetched panels into a figure."""

    draw: object                    # (ctx, panels) -> Figure
    n_eras: int | None              # required era count; None = any
    tight: bool = False


def _draw_single(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """One era, one map, no distribution — the per-run product the pipeline emits."""
    panel = panels[0]
    return plot_metric([(l.values, l.bounds) for l in panel.layers],
                       metric=ctx.metric, region_display=ctx.region.display,
                       res_label=_res_label(panel), period_slug=panel.period,
                       source_label=panel.source.display_label)


def _draw_multi(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Every era side by side on one colour scale and one extent."""
    return plot_metric_panels(panels, metric=ctx.metric,
                              region_display=ctx.region.display,
                              res_label=_res_label(panels[0]))


def _draw_delta(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Consecutive eras differenced pairwise, on one diverging zero-centred scale."""
    deltas = [_delta_panel(base, cand)
              for base, cand in zip(panels, panels[1:])]
    sources = sorted({p.source.display_label for p in panels})
    return plot_delta_panels(deltas, metric=ctx.metric,
                             region_display=ctx.region.display,
                             res_label=_res_label(panels[0]),
                             source_label=" + ".join(sources))


def _draw_portrait(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Baseline and candidate over their change — two eras, two scales, one figure."""
    base, cand = panels
    return plot_source_portrait(base, cand, _delta_panel(base, cand),
                                metric=ctx.metric,
                                region_display=ctx.region.display,
                                res_label=_res_label(base))


RENDERERS: dict[tuple[str, str, bool], Renderer] = {
    (RAW,   SINGLE,   False): Renderer(_draw_single,   n_eras=1,    tight=True),
    (RAW,   MULTI,    True):  Renderer(_draw_multi,    n_eras=None),
    (DELTA, SINGLE,    True):  Renderer(_draw_delta,    n_eras=None),
    (DELTA, PORTRAIT, False): Renderer(_draw_portrait, n_eras=2),
}


def _res_label(panel: MetricPanel) -> str:
    return " / ".join(f"{int(round(layer.res_m))} m" for layer in panel.layers)


def _delta_panel(base: MetricPanel, cand: MetricPanel) -> DeltaPanel:
    """Candidate − baseline per tier, on the shared region+tier grid (direct subtraction)."""
    return DeltaPanel(
        title=f"{cand.period} {cand.source.slug.upper()} − "
              f"{base.period} {base.source.slug.upper()}",
        layers=[RasterLayer(values=c.values - b.values, bounds=c.bounds, res_m=c.res_m)
                for b, c in zip(base.layers, cand.layers)],
    )


# --- stages -----------------------------------------------------------------

def _resolve(region_slug: str, metric_slug: str, eras: tuple[Era, ...], *,
             reduction_slug: str, type: str, layout: str,
             distribution: bool) -> PlotContext:
    """Resolve slugs to the figure's identity (mirrors ``pipeline._resolve``)."""
    ctx = PlotContext(
        region=RegionSpec.build(region_slug),
        metric=METRICS[metric_slug].with_reduction(REDUCTIONS[reduction_slug]),
        eras=eras, type=type, layout=layout, distribution=distribution,
    )
    log.info("Figure: %s %s/%s | Metric: %s | Reduction: %s | Region: %s | Eras: %s",
             ctx.type, ctx.layout, "dist" if ctx.distribution else "nodist",
             ctx.metric.slug, ctx.reduction, ctx.region.slug,
             ", ".join(e.label for e in ctx.eras))
    return ctx


def _assert_configured(ctx: PlotContext) -> None:
    """The configuration half: the layout must exist, and the era count must suit it."""
    renderer = RENDERERS.get(ctx.key)
    if renderer is None:
        available = ", ".join(f"{t}/{l}/{'dist' if d else 'nodist'}"
                              for t, l, d in sorted(RENDERERS))
        raise ValueError(
            f"No renderer for type={ctx.type!r} layout={ctx.layout!r} "
            f"distribution={ctx.distribution} — available: {available}.")

    eras = [e.label for e in ctx.eras]
    if renderer.n_eras is not None and len(eras) != renderer.n_eras:
        raise ValueError(f"Layout {ctx.layout!r} takes exactly {renderer.n_eras} era(s); "
                         f"got {len(eras)}: {eras}.")
    if ctx.type == DELTA and len(eras) < 2:
        raise ValueError(f"A delta needs at least two eras to difference; got {eras}.")


def _validate(ctx: PlotContext) -> list[list[ArchiveRef]]:
    """Reject an incoherent figure before a single raster is read.

    Two halves, both answerable without loading anything: the *configuration*, from the
    context alone, and the *archive*, from the ``.json`` manifests ``find_archived`` already
    reads to select a product. Returns the refs per era, coarse tier first, so ``_fetch``
    loads exactly what was approved here and nothing re-decides.
    """
    _assert_configured(ctx)
    refs = [[_locate(ctx, era, tier) for tier in ctx.tiers] for era in ctx.eras]

    flat = [ref for era_refs in refs for ref in era_refs]
    assert_one_reduction(flat, ctx.metric)   # archives match the order the figure claims
    assert_comparable(flat, ctx.metric)      # step counts share one observation unit
    _assert_shared_grid(refs)                # a delta subtracts cell-wise; panels share an extent
    log.info("Validated %d archived product(s) across %d era(s).", len(flat), len(refs))
    return refs


def _locate(ctx: PlotContext, era: Era, tier: str) -> ArchiveRef:
    """The newest archived product for one (era, tier), with the manifest that selected it."""
    npz, manifest = find_archived(ctx.region.slug, ctx.metric.slug,
                                  period_slug=era.period, source_slug=era.source,
                                  tier_level=tier, reduction_slug=ctx.reduction)
    return ArchiveRef(era=era, tier=tier, npz=npz, manifest=manifest)


def _assert_shared_grid(refs: list[list[ArchiveRef]]) -> None:
    """Every era must describe the same grid per tier, or the panels do not overlay.

    The region+tier grid is source- and period-invariant by construction, so a mismatch means
    the archives were written against different region definitions — which a delta would
    silently subtract cell-for-cell into nonsense. Corners closer than ``GRID_MATCH_CELLS``
    of a cell are the same grid: bounds are recomputed per run and round-tripped through
    JSON, so the same corner drifts in its last bits across eras.
    """
    for tier_refs in zip(*refs):
        first = tier_refs[0]
        tol = GRID_MATCH_CELLS * first.res_m
        shapes = {r.grid_shape for r in tier_refs}
        moved = any(abs(a - b) > tol
                    for r in tier_refs for a, b in zip(first.bounds, r.bounds))
        if len(shapes) > 1 or moved:
            raise ValueError(
                f"Tier {first.tier!r} archives disagree on the grid across eras "
                f"({', '.join(r.era.label for r in tier_refs)}): shapes={sorted(shapes)}, "
                f"bounds={sorted({r.bounds for r in tier_refs})}. The region+tier grid must "
                "be era-invariant.")


def _fetch(ctx: PlotContext, refs: list[list[ArchiveRef]]) -> list[MetricPanel]:
    """Load each approved ``.npz`` into its era's panel, coarse tier first."""
    panels = []
    for era_refs in refs:
        layers = [RasterLayer(values=np.load(r.npz)["values"],
                              bounds=r.bounds, res_m=r.res_m)
                  for r in era_refs]
        era = era_refs[0].era
        panels.append(MetricPanel(period=era.period, source=CHART_TABLES[era.source],
                                  layers=layers, reduction=ctx.reduction))
    log.info("Loaded %d raster(s).", sum(len(p.layers) for p in panels))
    return panels


def _render(ctx: PlotContext, panels: list[MetricPanel]) -> PlotProduct:
    """Draw the figure this configuration selects — the one dispatch seam over the renderers."""
    renderer = RENDERERS[ctx.key]
    return PlotProduct(figure=renderer.draw(ctx, panels), tight=renderer.tight)


def build(region_slug: str, metric_slug: str, eras: tuple[Era, ...], *,
          reduction_slug: str = MEDIAN_THEN_THRESHOLD.slug,
          type: str = RAW, layout: str = MULTI,
          distribution: bool = True) -> PlotProduct:
    """Build one figure from the archive; the caller writes it via ``export.save_figure``.

    Returns the figure rather than a path so the write stays one concern in one place —
    ``services.export`` owns where a product lands, this module owns what it looks like.
    """
    ctx = _resolve(region_slug, metric_slug, eras, reduction_slug=reduction_slug,
                   type=type, layout=layout, distribution=distribution)
    refs = _validate(ctx)
    return _render(ctx, _fetch(ctx, refs))


# --- CLI --------------------------------------------------------------------

def _era(spec: str) -> Era:
    """``period:source`` — e.g. ``2011-2020:sgrda``."""
    period, _, source = spec.partition(":")
    if not source:
        raise argparse.ArgumentTypeError(
            f"Era {spec!r} must be 'period:source', e.g. '2011-2020:sgrda'.")
    if source not in CHART_TABLES:
        raise argparse.ArgumentTypeError(
            f"Unknown source {source!r}; choose from {', '.join(sorted(CHART_TABLES))}.")
    return Era(period=period, source=source)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", choices=sorted(METRICS), metavar="METRIC")
    p.add_argument("region", choices=REGIONS, metavar="REGION")
    p.add_argument("--era", action="append", type=_era, dest="eras", required=True,
                   metavar="PERIOD:SOURCE",
                   help="Archived product to draw, repeatable and ordered "
                        "(a delta differences consecutive pairs).")
    p.add_argument("--type", choices=(RAW, DELTA), default=RAW,
                   help="Absolute values, or the signed change between eras.")
    p.add_argument("--layout", choices=(SINGLE, MULTI, PORTRAIT), default=MULTI,
                   help="One map, a panel grid, or a baseline/candidate/change portrait.")
    p.add_argument("--no-distribution", action="store_false", dest="distribution",
                   help="Drop the area-weighted value distribution beside each map.")
    p.add_argument("--reduction", choices=sorted(REDUCTIONS),
                   default=MEDIAN_THEN_THRESHOLD.slug,
                   help=f"Reduction order whose archives to read "
                        f"(default: {MEDIAN_THEN_THRESHOLD.slug}).")
    p.add_argument("--out", type=Path, required=True, metavar="PNG",
                   help="Where to write the figure.")
    return p.parse_args()


def main() -> None:
    from dotenv import load_dotenv

    from climatology.services.export import save_figure

    # Only on the CLI path: MAPBOX_TOKEN reaches `plot.basemap` through the environment, and
    # importing this module (as `pipeline` does) must not have the side effect of setting it.
    # Every other entry point — main, sweep, the composite scripts — bootstraps the same way.
    load_dotenv(Path(__file__).parents[2] / ".env")

    logging.basicConfig(level=logging.INFO, datefmt="%H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    product = build(args.region, args.metric, tuple(args.eras),
                    reduction_slug=args.reduction, type=args.type,
                    layout=args.layout, distribution=args.distribution)
    save_figure(product.figure, args.out, tight=product.tight)


if __name__ == "__main__":
    main()
