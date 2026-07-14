"""Derive two account-portable styles from the OGSL dark style.

The OGSL style's land comes from two tilesets *private* to `admin-ogsl`
(`land_layer_main_10m`, `7fn1vped`), so it cannot be cloned to another account as-is. It also
does not need to be: that land polygon is the coarse one that buries the river channels, and
the OSM landmask already overrides it. Everything actually used — hillshade, roads, labels —
comes from `mapbox-streets-v8` / `mapbox-terrain-v2`, which are public.

So the private-source layers are dropped and the land they painted is replaced by a flat
`background`; the OSM clip in climatology/utils/basemap.py cuts the water back out. The
symbol layers are split into a second style, which is what finally lets labels be composited
*unclipped* (halos included) instead of rescued by the luminance heuristic — the Static Images
API allows only one `setfilter` per request, so the split has to live in the style.

    iceclim_base.json     background + hillshade + roads   (no labels, no coastline)
    iceclim_labels.json   the 15 symbol layers             (transparent elsewhere)

Run:
    .venv/bin/python -m backend.probes.031_mapbox_basemap.make_styles
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env")

SRC_STYLE = "admin-ogsl/cmm9eq9ek001j01ry7a4h1j2b"
OUT = Path(__file__).parent / "style"

# Tilesets owned by admin-ogsl: private, so unusable from another account.
PRIVATE_TILESETS = {"admin-ogsl.land_layer_main_10m", "admin-ogsl.7fn1vped"}
# The source-layers those tilesets expose — the layers reading them are the ones to drop.
PRIVATE_SOURCE_LAYERS = {"land_layer_main_10m", "eastern_land_with_fjord_bigge-dz9gd7"}

# The fill the dropped land layers painted; the background inherits it so land keeps its tone.
LAND_FILL = "#14151f"
# A stock sprite: the OGSL style's own is bound to that style. Road shields may differ; text
# labels (the ones that matter here) do not depend on it.
SPRITE = "mapbox://sprites/mapbox/dark-v11"


def fetch_source_style() -> dict:
    """The OGSL style JSON (styles:read; the token is URL-restricted, so send the Referer)."""
    token = os.environ["MAPBOX_TOKEN"]
    url = f"https://api.mapbox.com/styles/v1/{SRC_STYLE}?access_token={token}"
    headers = {"Referer": referer} if (referer := os.getenv("MAPBOX_REFERER")) else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def public_sources(sources: dict) -> dict:
    """The style's sources with every private tileset stripped out of the composite."""
    out = {}
    for name, spec in sources.items():
        if not (url := spec.get("url", "")).startswith("mapbox://"):
            out[name] = spec
            continue
        kept = [t for t in url.removeprefix("mapbox://").split(",") if t not in PRIVATE_TILESETS]
        out[name] = {**spec, "url": "mapbox://" + ",".join(kept)}
    return out


def build(src: dict, name: str, layers: list[dict], *, background: str | None) -> dict:
    """One style: the shared sources/glyphs, a layer subset, optionally a flat land background."""
    if background:
        layers = [{"id": "land", "type": "background",
                   "paint": {"background-color": background}}] + layers
    return {
        "version": 8,
        "name": name,
        "sources": public_sources(src["sources"]),
        "sprite": SPRITE,
        "glyphs": src.get("glyphs", "mapbox://fonts/mapbox/{fontstack}/{range}.pbf"),
        "layers": layers,
    }


def main() -> None:
    src = fetch_source_style()
    layers = src["layers"]

    dropped = [L["id"] for L in layers if L.get("source-layer") in PRIVATE_SOURCE_LAYERS]
    base_layers = [L for L in layers
                   if L["type"] != "symbol" and L.get("source-layer") not in PRIVATE_SOURCE_LAYERS]
    label_layers = [L for L in layers if L["type"] == "symbol"]

    OUT.mkdir(parents=True, exist_ok=True)
    for fname, style in (
        ("iceclim_base.json", build(src, "ice-clim base (dark)", base_layers, background=LAND_FILL)),
        ("iceclim_labels.json", build(src, "ice-clim labels", label_layers, background=None)),
    ):
        (OUT / fname).write_text(json.dumps(style, indent=1))
        print(f"  wrote style/{fname}  ({len(style['layers'])} layers)")

    print(f"\ndropped {len(dropped)} private-source layers: {', '.join(dropped)}")
    print("remaining sources:",
          ", ".join(s.get("url", "") for s in public_sources(src["sources"]).values()))


if __name__ == "__main__":
    main()
