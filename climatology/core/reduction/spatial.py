"""Reduction across space: what ground each tier's raster cell actually accounts for.

The temporal reducers collapse a season's observations into one value per cell; this one
collapses a *tiered stack* of rasters into one flat (value, area) pairing. Tiers cover the
same ground at different resolutions, so a naive concatenation would count the overlap
twice and let a fine cell outvote a coarse one per unit of ground — `area_weights` resolves
that into a union, attributing each patch to the finest tier holding data there.

Consumed by the figures (the area-weighted distribution beside each map) and by probe 029,
which validates the de-overlap against an independent area truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from climatology.utils._types import DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.core.regions import Tier

# ``Tier.res_m`` is the *requested* resolution: build_grid rounds the cell count up
# (ceil) and then stretches the cells to span the wet bbox exactly, so true cells are
# slightly smaller than nominal, not square, and never off by more than ~1/width.
# Areas must therefore come from bounds/shape, never from res_m²; res_m is only a
# sanity anchor, so the check is a band and not an equality.
CELL_SIZE_TOL = 0.02


def _cell_size(shape: tuple[int, int], bounds: GridBounds,
               *, res_m: float | None = None) -> tuple[float, float]:
    """A raster's true (x, y) cell size from its bounds and shape, sanity-checked against the tier's nominal resolution."""
    height, width = shape
    xmin, ymin, xmax, ymax = bounds
    res_x, res_y = (xmax - xmin) / width, (ymax - ymin) / height
    if res_m is not None:
        lo, hi = res_m * (1.0 - CELL_SIZE_TOL), res_m * (1.0 + CELL_SIZE_TOL)
        if not (lo <= res_x <= hi and lo <= res_y <= hi):
            raise ValueError(
                f"Raster cell size ({res_x:g} × {res_y:g} m) is not within "
                f"{CELL_SIZE_TOL:.0%} of the tier's nominal resolution ({res_m:g} m): "
                "bounds, shape and grid res are out of sync."
            )
    return res_x, res_y


@dataclass(frozen=True)
class RasterLayer:
    """One tier's raster in a figure: its cells, its ground bounds, and the tier's authoritative resolution."""

    values: DataGrid
    bounds: GridBounds
    res_m: float          # Tier.res_m live; manifest "grid_res_m" when read back from an archive

    @classmethod
    def from_tier(cls, values: DataGrid, tier: Tier) -> "RasterLayer":
        """Build a layer from a live pipeline tier."""
        return cls(values, tier.grid.bounds, tier.res_m)

    @property
    def cell_size(self) -> tuple[float, float]:
        """(x, y) cell size, validated against ``res_m``."""
        return _cell_size(self.values.shape, self.bounds, res_m=self.res_m)

    @property
    def cell_area(self) -> float:
        """Ground area of one cell (m²)."""
        res_x, res_y = self.cell_size
        return res_x * res_y


def _deposit(coarse: RasterLayer, finer: RasterLayer, finer_area: np.ndarray) -> np.ndarray:
    """Drop each finer cell's ground area into whichever coarse cell contains its centre.

    ``finer_area`` is the finer tier's *own* area per cell — already stripped of
    whatever tiers finer still had claimed — so summing these deposits across tiers
    yields the union of the covered ground, not a double count of it.
    """
    height, width = coarse.values.shape
    xmin, _, _, ymax = coarse.bounds
    res_x, res_y = coarse.cell_size

    f_height, f_width = finer.values.shape
    f_res_x, f_res_y = finer.cell_size
    f_xmin, _, _, f_ymax = finer.bounds
    xs = f_xmin + (np.arange(f_width) + 0.5) * f_res_x
    ys = f_ymax - (np.arange(f_height) + 0.5) * f_res_y     # origin="upper": row 0 sits at ymax
    grid_x, grid_y = np.meshgrid(xs, ys)

    claims = finer_area > 0.0
    cols = np.floor((grid_x[claims] - xmin) / res_x).astype(int)
    rows = np.floor((ymax - grid_y[claims] ) / res_y).astype(int)
    inside = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)

    covered = np.zeros(height * width)
    np.add.at(covered, rows[inside] * width + cols[inside], finer_area[claims][inside])
    return covered.reshape(height, width)


def area_weights(layers: list[RasterLayer]) -> tuple[np.ndarray, np.ndarray]:
    """Every finite cell's value and the ground area (m²) it alone stands for.

    Tiers run coarse -> fine and cover the same ground, so each patch is attributed to
    the *finest* tier holding data there: a tier keeps its cell area minus what the finer
    tiers already claim. Resolving it finest-first — each tier depositing its own,
    already-deduplicated area upward — makes the subtraction a union rather than a sum,
    which matters as soon as a region has three tiers whose finer two overlap each other.

    Counting raw cells instead would let a 100 m cell and a 1000 m cell speak equally,
    and the fine tier would outvote the coarse one 100:1 per unit of ground.
    """
    own: list[np.ndarray] = [np.empty(0)] * len(layers)
    for i in reversed(range(len(layers))):          # finest -> coarsest
        layer = layers[i]
        claimed = np.zeros(layer.values.shape)
        for j in range(i + 1, len(layers)):
            claimed += _deposit(layer, layers[j], own[j])
        area = np.clip(layer.cell_area - claimed, 0.0, layer.cell_area)
        area[~np.isfinite(layer.values)] = 0.0      # no data -> claims no ground
        own[i] = area

    finite = [np.isfinite(layer.values) for layer in layers]
    values = np.concatenate([layer.values[m] for layer, m in zip(layers, finite)])
    weights = np.concatenate([area[m] for area, m in zip(own, finite)])
    return values, weights
