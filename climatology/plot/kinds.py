"""The two axes a figure is classified on, and the dispatch keys they are.

Every stage of the figure pipeline keys a table on one of these — ``_LABELLERS``, ``_SCALES``,
``_LAYOUTS``, ``_RENDERERS`` on the kind, ``_ORDERS`` and the delta tails on the type — and no
stage owns them. Their own module for exactly that reason: parked in ``labels`` they made the
*text* concern a dependency of ``colors``, ``layout`` and ``export``, which left text -> geometry
as the one import direction still open and so kept ``labels`` from asking ``layout`` whether a
lattice is legible. A leaf module imports nothing and closes no loop.
"""

from __future__ import annotations

RAW, DELTA = "raw", "delta"

# What a figure draws, and therefore which family of objects each stage resolves. Not
# configured but *derived* from the metric (``PlotContext.kind``): the two product layouts are
# located in different spaces, so which one a run archived is not a presentation choice.
# Orthogonal to RAW/DELTA, which asks whether a raster figure shows values or their change.
RASTER, SERIES = "raster", "series"
