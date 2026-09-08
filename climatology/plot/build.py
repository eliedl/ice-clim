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
    python -m climatology.plot.build METRIC --region R --period P --source S --reduction X

A product is identified by region, period, source and reduction. Region is pinned — panels
must overlay on one grid — so the figure branches on the other three: pass ``a:b:c`` to any
of ``--period``, ``--source``, ``--reduction`` and it becomes the axis of comparison, with the
pinned coordinates broadcast across it. Run the sweep first; every product named must already
be archived.

    # one product, one map: the same figure the pipeline emits per run
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
    plot_delta_panels,
    plot_metric,
    plot_metric_panels,
    plot_source_portrait,
)
from climatology.plot.validate import assert_comparable
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

# The product coordinates a figure can branch on, in title order. Region is the fourth and
# is pinned: panels that do not share a grid cannot overlay, let alone be differenced.
COORDS = ("period", "source", "reduction")

GRID_MATCH_CELLS = 0.01   # bounds within 1/100 of a cell are the same grid


# --- context ----------------------------------------------------------------

@dataclass(frozen=True)
class Product:
    """One archived product's coordinates — a figure's unit of comparison."""

    period: str
    source: str
    reduction: str = MEDIAN_THEN_THRESHOLD.slug

    @property
    def label(self) -> str:
        return f"{self.period} {self.source.upper()} {self.reduction}"


@dataclass(frozen=True)
class PlotContext:
    """Resolved, immutable identity of one figure: what to draw, and how to lay it out.

    ``type``/``layout``/``distribution`` are the presentation axes the CLI sets; the rest
    names the archived products the figure is built from. A delta reads its products pairwise
    (candidate − baseline), so ``products`` is ordered and its length is layout-dependent —
    ``_validate`` is what holds that rule.
    """

    region: RegionSpec
    metric: MetricSpec
    products: tuple[Product, ...]
    type: str = RAW                 # raw | delta
    layout: str = MULTI             # single | multi | portrait
    distribution: bool = True

    @property
    def tiers(self) -> list[str]:
        return [tier.level for tier in self.region.tiers]

    @property
    def axes(self) -> tuple[str, ...]:
        """The coordinates that actually differ across the products — what a panel title must
        name, and by complement what the subtitle can state once for the whole figure."""
        return tuple(name for name in COORDS
                     if len({getattr(p, name) for p in self.products}) > 1)

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

    product: Product
    tier: str
    npz: Path
    manifest: dict

    @property
    def source(self) -> ChartTable:
        return CHART_TABLES[self.product.source]

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


# --- naming -----------------------------------------------------------------
# Which coordinates distinguish a panel depends on which one the figure branched on, so the
# titles are decided here and handed to the renderers as data. Varying coordinates title the
# panels; pinned ones are stated once, in the subtitle.

def _coord_text(product: Product) -> dict[str, str]:
    """Each coordinate as it should read, already cased — the source and reduction are slugs
    and stay lowercase, so the assembled title must never be re-cased as a whole."""
    return {"period": f"Winters {product.period}", "source": product.source,
            "reduction": product.reduction}


def _panel_title(ctx: PlotContext, product: Product) -> str:
    """Panel heading: the coordinates that distinguish this product from the figure's others."""
    named = ctx.axes or ("period", "source")   # a lone product still says what it is
    text = _coord_text(product)
    # "·", not an em dash: a delta title joins two of these with "−", and the two dashes
    # are indistinguishable at title size.
    return " · ".join(text[name] for name in COORDS if name in named)


def _subtitle(ctx: PlotContext) -> str:
    """Figure subtitle: the coordinates every panel shares (the varying ones title the panels)."""
    text = _coord_text(ctx.products[0])
    return " · ".join(text[name] for name in COORDS if name not in ctx.axes)


# --- renderer registry ------------------------------------------------------
# One row per (type, layout, distribution) the archive can actually produce. A combination
# absent here is not silently approximated — `_validate` names it and the available ones.

@dataclass(frozen=True)
class Renderer:
    """How one configuration turns fetched panels into a figure."""

    draw: object                    # (ctx, panels) -> Figure
    n_products: int | None          # required product count; None = any
    tight: bool = False


def _draw_single(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """One product, one map, no distribution — the per-run product the pipeline emits."""
    panel = panels[0]
    return plot_metric([(l.values, l.bounds) for l in panel.layers],
                       metric=ctx.metric, region_display=ctx.region.display,
                       res_label=_res_label(panel), period_slug=panel.period,
                       source_label=panel.source.display_label)


def _draw_multi(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Every product side by side on one colour scale and one extent."""
    return plot_metric_panels(panels, metric=ctx.metric,
                              region_display=ctx.region.display,
                              res_label=_res_label(panels[0]))


def _draw_delta(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Consecutive products differenced pairwise, on one diverging zero-centred scale."""
    deltas = [_delta_panel(base, cand)
              for base, cand in zip(panels, panels[1:])]
    sources = sorted({p.source.display_label for p in panels})
    return plot_delta_panels(deltas, metric=ctx.metric,
                             region_display=ctx.region.display,
                             res_label=_res_label(panels[0]),
                             source_label=" + ".join(sources))


def _draw_portrait(ctx: PlotContext, panels: list[MetricPanel]) -> Figure:
    """Baseline and candidate over their change — two products, two scales, one figure."""
    base, cand = panels
    return plot_source_portrait(base, cand, _delta_panel(base, cand),
                                metric=ctx.metric,
                                region_display=ctx.region.display,
                                res_label=_res_label(base),
                                subtitle=_subtitle(ctx),
                                distribution=ctx.distribution)


RENDERERS: dict[tuple[str, str, bool], Renderer] = {
    (RAW,   SINGLE,   False): Renderer(_draw_single,   n_products=1,    tight=True),
    (RAW,   MULTI,    True):  Renderer(_draw_multi,    n_products=None),
    (DELTA, SINGLE,   True):  Renderer(_draw_delta,    n_products=None),
    (DELTA, PORTRAIT, False): Renderer(_draw_portrait, n_products=2),
    (DELTA, PORTRAIT, True):  Renderer(_draw_portrait, n_products=2),
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

def _resolve(region_slug: str, metric_slug: str, products: tuple[Product, ...], *,
             type: str, layout: str, distribution: bool) -> PlotContext:
    """Resolve slugs to the figure's identity (mirrors ``pipeline._resolve``).

    ``metric`` is bound to the first product's reduction. Everything the metric is asked for
    downstream — its title, its tick formatter, whether it counts steps — is order-independent;
    the order-dependent labels are taken per panel, from that panel's own reduction.
    """
    ctx = PlotContext(
        region=RegionSpec.build(region_slug),
        metric=METRICS[metric_slug].with_reduction(REDUCTIONS[products[0].reduction]),
        products=products, type=type, layout=layout, distribution=distribution,
    )
    log.info("Figure: %s %s/%s | Metric: %s | Region: %s | Branching on: %s | Products: %s",
             ctx.type, ctx.layout, "dist" if ctx.distribution else "nodist",
             ctx.metric.slug, ctx.region.slug, ", ".join(ctx.axes) or "nothing",
             ", ".join(p.label for p in ctx.products))
    return ctx


def _assert_configured(ctx: PlotContext) -> None:
    """The configuration half: the layout must exist, and the product count must suit it."""
    renderer = RENDERERS.get(ctx.key)
    if renderer is None:
        available = ", ".join(f"{t}/{l}/{'dist' if d else 'nodist'}"
                              for t, l, d in sorted(RENDERERS))
        raise ValueError(
            f"No renderer for type={ctx.type!r} layout={ctx.layout!r} "
            f"distribution={ctx.distribution} — available: {available}.")

    labels = [p.label for p in ctx.products]
    if renderer.n_products is not None and len(labels) != renderer.n_products:
        raise ValueError(f"Layout {ctx.layout!r} takes exactly {renderer.n_products} "
                         f"product(s); got {len(labels)}: {labels}.")
    if ctx.type == DELTA and len(labels) < 2:
        raise ValueError(f"A delta needs at least two products to difference; got {labels}.")


def _validate(ctx: PlotContext) -> list[list[ArchiveRef]]:
    """Reject an incoherent figure before a single raster is read.

    Two halves, both answerable without loading anything: the *configuration*, from the
    context alone, and the *archive*, from the ``.json`` manifests ``find_archived`` already
    reads to select a product. Returns the refs per product, coarse tier first, so ``_fetch``
    loads exactly what was approved here and nothing re-decides.
    """
    _assert_configured(ctx)
    refs = [[_locate(ctx, product, tier) for tier in ctx.tiers] for product in ctx.products]

    flat = [ref for product_refs in refs for ref in product_refs]
    assert_comparable(flat, ctx.metric)      # step counts share one observation unit
    _assert_shared_grid(refs)                # a delta subtracts cell-wise; panels share an extent
    log.info("Validated %d archived product(s).", len(flat))
    return refs


def _locate(ctx: PlotContext, product: Product, tier: str) -> ArchiveRef:
    """The newest archived raster for one (product, tier), with the manifest that selected it."""
    npz, manifest = find_archived(ctx.region.slug, ctx.metric.slug,
                                  period_slug=product.period, source_slug=product.source,
                                  tier_level=tier, reduction_slug=product.reduction)
    return ArchiveRef(product=product, tier=tier, npz=npz, manifest=manifest)


def _assert_shared_grid(refs: list[list[ArchiveRef]]) -> None:
    """Every product must describe the same grid per tier, or the panels do not overlay.

    The region+tier grid is source-, period- and reduction-invariant by construction, so a
    mismatch means the archives were written against different region definitions — which a
    delta would silently subtract cell-for-cell into nonsense. Corners closer than
    ``GRID_MATCH_CELLS`` of a cell are the same grid: bounds are recomputed per run and
    round-tripped through JSON, so the same corner drifts in its last bits across products.
    """
    for tier_refs in zip(*refs):
        first = tier_refs[0]
        tol = GRID_MATCH_CELLS * first.res_m
        shapes = {r.grid_shape for r in tier_refs}
        moved = any(abs(a - b) > tol
                    for r in tier_refs for a, b in zip(first.bounds, r.bounds))
        if len(shapes) > 1 or moved:
            raise ValueError(
                f"Tier {first.tier!r} archives disagree on the grid across products "
                f"({', '.join(r.product.label for r in tier_refs)}): shapes={sorted(shapes)}, "
                f"bounds={sorted({r.bounds for r in tier_refs})}. The region+tier grid must "
                "be product-invariant.")


def _fetch(ctx: PlotContext, refs: list[list[ArchiveRef]]) -> list[MetricPanel]:
    """Load each approved ``.npz`` into its product's panel, coarse tier first."""
    panels = []
    for product_refs in refs:
        layers = [RasterLayer(values=np.load(r.npz)["values"],
                              bounds=r.bounds, res_m=r.res_m)
                  for r in product_refs]
        product = product_refs[0].product
        panels.append(MetricPanel(title=_panel_title(ctx, product), period=product.period,
                                  source=CHART_TABLES[product.source], layers=layers,
                                  reduction=product.reduction))
    log.info("Loaded %d raster(s).", sum(len(p.layers) for p in panels))
    return panels


def _render(ctx: PlotContext, panels: list[MetricPanel]) -> PlotProduct:
    """Draw the figure this configuration selects — the one dispatch seam over the renderers."""
    renderer = RENDERERS[ctx.key]
    return PlotProduct(figure=renderer.draw(ctx, panels), tight=renderer.tight)


def build(region_slug: str, metric_slug: str, products: tuple[Product, ...], *,
          type: str = RAW, layout: str = MULTI,
          distribution: bool = True) -> PlotProduct:
    """Build one figure from the archive; the caller writes it via ``export.save_figure``.

    Returns the figure rather than a path so the write stays one concern in one place —
    ``services.export`` owns where a product lands, this module owns what it looks like.
    """
    ctx = _resolve(region_slug, metric_slug, products,
                   type=type, layout=layout, distribution=distribution)
    refs = _validate(ctx)
    return _render(ctx, _fetch(ctx, refs))


# --- CLI --------------------------------------------------------------------

def _axis(name: str, choices: tuple[str, ...] | None = None):
    """An argparse type for one product coordinate as a branch: ``a`` or ``a:b:c``."""
    def parse(spec: str) -> tuple[str, ...]:
        values = tuple(spec.split(":"))
        if choices is not None:
            bad = [v for v in values if v not in choices]
            if bad:
                raise argparse.ArgumentTypeError(
                    f"Unknown {name} {bad}; choose from {', '.join(sorted(choices))}.")
        return values
    return parse


def _broadcast(periods: tuple[str, ...], sources: tuple[str, ...],
               reductions: tuple[str, ...]) -> tuple[Product, ...]:
    """Zip the coordinate axes into products, broadcasting the pinned (length-1) ones.

    One branch length is allowed beside 1: a coordinate is either held across the figure or
    carries one value per panel. ``--reduction a:b`` against ``--period x:y:z`` is a mistake,
    not a request for the six-panel cross product.
    """
    axes = {"period": periods, "source": sources, "reduction": reductions}
    n = max(len(values) for values in axes.values())
    ragged = {k: v for k, v in axes.items() if len(v) not in (1, n)}
    if ragged:
        raise ValueError(
            f"Coordinate axes must be length 1 or {n}; got "
            + ", ".join(f"--{k} with {len(v)}" for k, v in ragged.items())
            + ". Pin a coordinate to one value, or give it one value per panel.")
    return tuple(Product(**{k: v[0] if len(v) == 1 else v[i] for k, v in axes.items()})
                 for i in range(n))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", choices=sorted(METRICS), metavar="METRIC")
    p.add_argument("--region", choices=REGIONS, required=True, metavar="REGION",
                   help="Pinned across the figure — panels must overlay on one grid.")
    p.add_argument("--period", type=_axis("period"), default=("2011-2020",),
                   metavar="YYYY-YYYY[:...]",
                   help="Climatology period(s) in winters; colon-separated to branch.")
    p.add_argument("--source", type=_axis("source", tuple(CHART_TABLES)),
                   default=("sgrda",), metavar="SOURCE[:...]",
                   help=f"Chart table(s); colon-separated to branch. "
                        f"Choices: {', '.join(sorted(CHART_TABLES))}.")
    p.add_argument("--reduction", type=_axis("reduction", tuple(REDUCTIONS)),
                   default=(MEDIAN_THEN_THRESHOLD.slug,), metavar="REDUCTION[:...]",
                   help=f"Reduction order(s) whose archives to read; colon-separated to "
                        f"branch. Choices: {', '.join(sorted(REDUCTIONS))}.")
    p.add_argument("--type", choices=(RAW, DELTA), default=RAW,
                   help="Absolute values, or the signed change between products.")
    p.add_argument("--layout", choices=(SINGLE, MULTI, PORTRAIT), default=MULTI,
                   help="One map, a panel grid, or a baseline/candidate/change portrait.")
    p.add_argument("--no-distribution", action="store_false", dest="distribution",
                   help="Drop the area-weighted value distribution beside each map.")
    p.add_argument("--out", type=Path, required=True, metavar="PNG",
                   help="Where to write the figure.")
    return p.parse_args()


def main() -> None:
    from dotenv import load_dotenv

    from climatology.services.export import save_figure

    # Only on the CLI path: MAPBOX_TOKEN reaches `plot.basemap` through the environment, and
    # importing this module (as `pipeline` does) must not have the side effect of setting it.
    # Every other entry point — main, sweep — bootstraps the same way.
    load_dotenv(Path(__file__).parents[2] / ".env")

    logging.basicConfig(level=logging.INFO, datefmt="%H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    products = _broadcast(args.period, args.source, args.reduction)
    product = build(args.region, args.metric, products, type=args.type,
                    layout=args.layout, distribution=args.distribution)
    save_figure(product.figure, args.out, tight=product.tight)


if __name__ == "__main__":
    main()
