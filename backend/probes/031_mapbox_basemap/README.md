# Probe 031 — OGSL Mapbox dark style as a basemap over the metric rasters

## Hypothesis

The dark basemap behind nautilo.ca (`admin-ogsl` / `production-nautilo-theme-sombre`) can
replace the synthetic dark theme in `climatology/services/plot.py` — flat `DARK_OCEAN` fill
plus a flat `DARK_LAND` polygon paint — giving the climatology maps a real basemap (land
texture, hillshade, coastal town labels) **without compromising the data**: the ice values
must stay at full saturation, and the coastline must stay accurate enough for the river
estuaries the metrics actually resolve.

## Method

The style is rendered through the **Static Images API**, warped into the grid CRS, clipped to
the OSM landmask, and drawn **over** the metric rasters. Run on Manicouagan /
`season_duration_10` / 2011–2020 / sgrda, read back from the pipeline's own archives (no
probe-local recomputation) — Manicouagan holds the Outardes and Manicouagan river mouths,
which is exactly where the coastline question bites.

    fetch  Static Images render, coastline stroke suppressed at request time (setfilter)
    warp   EPSG:3857 -> EPSG:32198   (the API only ever renders Web Mercator)
    clip   drop the render over OSM water, luminance-aware so labels survive
    draw   over the data; OSM supplies the single coastline, in DARK_COAST

Four figures, one per claim the recipe rests on.

| figure | claim |
|---|---|
| `1_registration` | the warped render lands on the OSM coastline |
| `2_over_data` | the style's water is a true alpha hole, so "basemap over data" works |
| `3_coastline` | Mapbox's custom land buries the Rivière-aux-Outardes; OSM does not |
| `4_label_clip` | a hard clip crops labels overhanging the sea; the luminance clip does not |

## Run

```bash
MAPBOX_TOKEN=... MAPBOX_REFERER=... \
  .venv/bin/python -m backend.probes.031_mapbox_basemap.probe [--recompute]
```

Renders are cached on disk by `climatology.utils.basemap` (`~/.cache/ice-clim/basemap/`),
so re-runs are offline; `--recompute` drops the cache and re-fetches.

## Outcome (2026-07-14)

**The recipe works and is now implemented in `climatology/utils/basemap.py`, wired into
both `plot_metric` and `plot_metric_panels`.** Four findings carried the design.

### 1. The style renders water as a true alpha hole — so the basemap goes *over* the data

The Static PNG is a paletted image with a transparency index: **72.6 % of pixels are fully
transparent** (sea) and 26.8 % opaque (land, hillshade, labels). The style paints land and
leaves water unpainted. So the render composites *over* the metric rasters at full opacity —
land and coastal towns on top, ice values showing through the sea undimmed. No alpha blend,
no chroma-key.

The one trap: `PIL.Image.convert("RGB")` **discards that alpha and fills the sea with black**,
which hides the data completely. `convert("RGBA")` is load-bearing, and is commented as such.

### 2. The 3857 → 32198 warp registers

The grid is EPSG:32198 (NAD83 / Québec Lambert); Mapbox only renders Web Mercator. Requesting
a bbox whose *Mercator* aspect matches the requested pixel size (so Mapbox adds no padding),
then reprojecting with `rasterio.warp`, puts the rendered coastline on the OSM coastline to
sub-pixel accuracy across Gaspé, Anticosti, the Îles-de-la-Madeleine and the north shore
(`1_registration`). No projection compromise, no need to replot in 3857.

### 3. Mapbox's coastline is coarser than ours in the river channels — and zoom cannot fix it

The style carries **no `mapbox-streets` water fill**; its coastline comes entirely from two
custom OGSL sources, swapped by a `fill-opacity` zoom expression at **zoom 4.0 → 4.01**:

| layer | source | role |
|---|---|---|
| `zoom-out-land-layer-main` | `admin-ogsl.land_layer_main_10m` | coarse, below z4 |
| `zoom-in-eastern-land-with-fjord` | `admin-ogsl.7fn1vped` | fjord-resolving, above z4 |

Every regional render sits far above z4.01, so it is **already on the finest land layer the
style has**. At 15.6 m/px — 3× the zoom of a full-region render — the **Rivière-aux-Outardes
is still buried under Mapbox land**, while the OSM landmask carves the channel and the metric
has real ice values inside it (`3_coastline`). Higher zoom changes pixel density, not the
geometry baked into the custom polygon, so it cannot resolve the river. Mapbox paints 58.7 %
of the Outardes window as land against OSM's 56.8 % — that ~2 % delta *is* the rivers.

**Therefore the landmask, not the basemap, is authoritative for land/water.** The render is
clipped to the OSM display mask (`LAND_DISPLAY_PATH`), which is the mask `plot.py` already
trusts, and the river opens up with its data visible.

### 4. One `setfilter` per request — which decides how each unwanted layer is removed

The Static Images API takes request-time `layer_id` + `setfilter`. An always-false filter
renders a layer empty; this suppresses the style's own light coastline stroke (the bright rim
that skimmed the data edge) — **21 564 → 0** coastline pixels, no clone required. OSM then
supplies the single coastline, drawn in `DARK_COAST`.

But the API accepts **exactly one** pair per request: measured **n=1 → 200, n≥2 → 422**,
independent of URL length. So the 15 label layers *cannot* be split into a labels-only pass
from query params. That matters because the render flattens land, hillshade and labels into
one raster: a hard clip to the landmask **crops every label glyph overhanging the sea**
("Pointe-Lebel" cut to "Pointe-", "Baie des Anglais" erased entirely).

The shipped workaround is a **luminance-aware clip**: over water, drop only *dark* pixels
(land fill ≈ luma 21, hillshade) and keep *light* ones (label glyphs ≈ luma 200). It
recovers **2 366 label pixels** the hard clip destroyed (`4_label_clip`). Its one cost is that
Mapbox's dark label *halos* are themselves dark, so over-water labels lose their halo and sit
directly on the colormap at slightly reduced contrast.

## Caveats / open items

- **The token is borrowed and URL-restricted.** The OGSL public token is scoped to
  `nautilo.ca`: the API 403s without a matching `Referer`, so `MAPBOX_REFERER` must be set.
  Every render also bills map-loads to OGSL's account. Used with the account owner's
  permission; not a durable arrangement.
- **The clean label fix needs a style split, not a query param.** Cloning the style into a
  personal Mapbox account and splitting it into a *base* style (fills/lines/hillshade) and a
  *labels* style would let labels be composited fully unclipped, halos included, retiring the
  luminance heuristic. This also retires the borrowed token and the referer. Both custom
  sources (`land_layer_main_10m`, `7fn1vped`) are owned by `admin-ogsl` and are the thing to
  check for cloneability.
- **Attribution.** Renders are requested with `attribution=false&logo=false`, so the credit is
  owed in the figure: `_footer` prints `© Mapbox © OpenStreetMap contributors` whenever a
  basemap was drawn.