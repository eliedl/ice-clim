"""Figure output: writing a rendered figure to disk."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

PANEL_NCOLS = 2   # 4 periods -> 2 x 2


def save_figure(fig, png_path: Path, *, tight: bool = True) -> None:
    """Write the figure to disk under the dark theme.

    ``tight=False`` keeps the figure's own margins: a tight bbox crops each side down to
    the artists on it, which pulls a centred suptitle off-centre whenever the two sides
    are cropped by different amounts.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, bbox_inches="tight" if tight else None,
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
