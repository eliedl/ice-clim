"""Probe 035 — kamou-roi domain-series CSV export, on the grid's true cell.

Exports the archived `kamou-roi` concentration series (`.npz` + manifest) as one wide CSV:
winters down the rows, days of season across the columns, ice-covered area in km2 in the
cells. `plot/render.py` is the only other consumer of this product and it scales by the
*nominal* `res_m ** 2`; this exports on the grid's **true** cell area, so the CSV and the
plotted curve differ by a known -1.2 % (see README).

The emitted file is a standalone deliverable: its `#` preamble is written for whoever
analyses the numbers, and names no part of this codebase.

Read-only: the archive and the region geometry. No DB, no write-back to `climatology/output/`.

Run:
    .venv/bin/python -m backend.probes.035_kamou_roi_series_csv.probe
    .venv/bin/python -m backend.probes.035_kamou_roi_series_csv.probe --region manic-roi \
        --period 1981-2010 --source sgrdr
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from climatology.core.context import RunContext
from climatology.core.export import find_archived
from climatology.core.reduction.temporal import SeriesLayer
from climatology.core.regions import Tier
from climatology.plot.labels import REGION_LABELS
from climatology.services.calendar import season_day_label
from climatology.utils._types import GRID_CRS

OUTPUT_DIR = Path(__file__).parent / "output"

REGION = "kamou-roi"
METRIC = "landfast_concentration"
PERIOD = "2007-2026"
SOURCE = "sgrda"
REDUCTION = "series"

KM2 = 1e6
AREA_DECIMALS = 4      # ~100 m2, two orders under the 2 469 m2 cell this region resolves


def _cell_area(manifest: dict, tier: Tier) -> tuple[float, str]:
    """The true ground area of one cell (m2), and where it was read from.

    Both cases are live: archives written since the ``cell_area_m2`` manifest field carry
    their own cell, and those written before it carry no geometry at all — a series manifest
    records no bounds and no shape — so the only remaining source is the region rebuilt from
    its slug. That fallback holds only while the live grid *is* the grid the product ran on,
    for which the nominal resolutions agreeing is the available evidence.
    """
    if "cell_area_m2" in manifest:
        return float(manifest["cell_area_m2"]), "manifest field 'cell_area_m2'"

    if manifest["grid_res_m"] != tier.res_m:
        raise ValueError(
            f"Archive was written at {manifest['grid_res_m']} m but the region table now "
            f"plans {tier.res_m} m for tier '{tier.level}': the live grid is not the grid "
            "this product ran on, so its cell area cannot be recovered. Re-run the sweep.")
    return tier.grid.cell_area, f"live '{tier.level}' tier (archive predates cell_area_m2)"


def _columns(days: np.ndarray) -> pd.MultiIndex:
    """The two-row column header: calendar MM-DD over the day-of-season ordinal it encodes."""
    return pd.MultiIndex.from_arrays(
        [[season_day_label(d) for d in days], [int(d) for d in days]],
        names=["month_day", "day_of_season"])


def _frame(layer: SeriesLayer, cell_area: float) -> pd.DataFrame:
    """The series as a winters x days table of ice-covered area in km2.

    NaN is kept as NaN and writes as an empty cell: a day a season published no chart is
    not a day it held no ice, and zero would assert the second.
    """
    return pd.DataFrame(layer.values * cell_area / KM2,
                        index=pd.Index(layer.seasons, name="season"),
                        columns=_columns(layer.days))


def _preamble(manifest: dict, layer: SeriesLayer, cell_area: float) -> str:
    """The `#` header block: what a reader needs to interpret the values and compute on them.

    The metadata a two-row header structurally cannot carry. A MultiIndex says a column *is*
    day 136; it has nowhere to say what 136 is counted from, because the epoch is a property
    of the coordinate system and not of any one column.
    """
    source = RunContext.build(manifest["region"], manifest["metric"], manifest["period"],
                              manifest["source"], manifest["reduction"]).source
    first, last = int(layer.days[0]), int(layer.days[-1])
    lines = [
        "Superficie en km² couverte par la glace, par hiver et par jour de saison.",
        "",
        f"Région     {REGION_LABELS[manifest['region']]}",
        f"Période    hivers {layer.seasons[0]} à {layer.seasons[-1]}",
        f"Source     {source.display_label}",
        f"Généré     {datetime.now():%Y-%m-%d}",
        "",
        "COLONNES   Deux lignes d'en-tête, une colonne par jour observé.",
        "  ligne 1  month_day      date, format MM-DD.",
        "  ligne 2  day_of_season  jours écoulés depuis le 1er septembre (jour 0 = 09-01).",
        "                          L'année de référence n'est pas bissextile : le 29 février",
        "                          est absent de l'axe.",
        f"           Étendue : jour {first} ({season_day_label(first)}) à "
        f"jour {last} ({season_day_label(last)}), pas constant de {manifest['day_step']} jour(s).",
        "",
        "LIGNES     Un hiver par ligne, désigné par l'année où il se termine :",
        f"           la ligne {layer.seasons[-1]} est l'hiver "
        f"{layer.seasons[-1] - 1}-{layer.seasons[-1]}. {len(layer.seasons)} hivers.",
        "",
        "VALEURS    Superficie de glace en km².",
        "           Cellule vide = aucune carte publiée ce jour-là pour cet hiver. C'est une",
        "           donnée manquante, et non une absence de glace : à exclure des",
        "           statistiques plutôt qu'à traiter comme un zéro.",
        "",
        f"GRILLE     Cellule de {cell_area:.4f} m². Projection EPSG:{GRID_CRS} "
        "(NAD83 / Québec Lambert).",
        "",
        "LECTURE    pandas.read_csv(/path/vers/le/fichier.csv, comment='#', header=[0, 1], index_col=0)",
    ]
    return "".join(f"# {line}\n".replace(" \n", "\n") for line in lines)


def _write(frame: pd.DataFrame, preamble: str, path: Path) -> None:
    """Write the preamble and the table into one file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(preamble)
        frame.to_csv(fh, float_format=f"%.{AREA_DECIMALS}f", lineterminator="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an archived domain series as CSV.")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--metric", default=METRIC)
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--source", default=SOURCE)
    args = parser.parse_args()

    ctx = RunContext.build(args.region, args.metric, args.period, args.source, REDUCTION)
    archived = find_archived(ctx)
    if len(archived) != 1:
        raise ValueError(f"Expected one archived tier for {args.region}, found {len(archived)}: "
                         "a domain series compresses one tier's domain away, and this export "
                         "has no rule for combining two.")
    npz, manifest = archived[0]

    layer = SeriesLayer.from_manifest(np.load(npz)["values"], manifest)
    cell_area, provenance = _cell_area(manifest, ctx.region.tiers[0])
    frame = _frame(layer, cell_area)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = OUTPUT_DIR / f"{stamp}_{npz.stem}.csv"
    _write(frame, _preamble(manifest, layer, cell_area), path)

    nominal = manifest["grid_res_m"] ** 2
    print(f"cell area  {cell_area:.4f} m2 ({provenance}); "
          f"nominal {nominal:.1f} m2, {100.0 * (cell_area / nominal - 1.0):+.3f} %")
    print(f"table      {frame.shape[0]} winters x {frame.shape[1]} days, "
          f"peak {np.nanmax(frame.to_numpy()):.3f} km2")
    print(f"written    {path}")


if __name__ == "__main__":
    main()
