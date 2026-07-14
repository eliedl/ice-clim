# Probe 031 — OGSL Mapbox dark style as a basemap over the metric rasters

## Hypothesis

The dark basemap behind nautilo.ca (`admin-ogsl` / `production-nautilo-theme-sombre`) can
replace the synthetic dark theme in `climatology/services/plot.py` — flat `DARK_OCEAN` fill
plus a flat `DARK_LAND` polygon paint — giving the climatology maps a real basemap (land
texture, hillshade, coastal town labels) **without compromising the data**: the ice values
must stay at full saturation, and the coastline must stay accurate enough for the river
estuaries the metrics actually resolve.

## Method

A style is rendered through the **Static Images API**, warped into the grid CRS, clipped to
the OSM landmask, and drawn **over** the metric rasters. Run on Manicouagan /
`season_duration_10` / 2011–2020 / sgrda, read back from the pipeline's own archives (no
probe-local recomputation) — Manicouagan holds the Outardes and Manicouagan river mouths,
which is exactly where the coastline question bites.

Two stacks are kept side by side, for lineage.

**v1 — the OGSL style, borrowed (superseded, `--legacy`).** One flattened render we did not
own, made usable by two workarounds:

    fetch  admin-ogsl style, coastline stroke suppressed at request time (setfilter)
    clip   drop the render over OSM water, *luminance-aware* so labels survive
    draw   over the data

**v2 — two styles we own (current; what `climatology/utils/basemap.py` implements).** The
split is the design: it makes the clip exact and leaves the labels alone.

    fetch  two styles on the `eliedl` account, both on *public* Mapbox tilesets —
             base    flat land + hillshade + roads, opaque, no coastline of its own
             labels  the symbol layers alone, transparent elsewhere
    warp   EPSG:3857 -> EPSG:32198   (the API only ever renders Web Mercator)
    clip   drop the *base* over OSM water — exact, no heuristic
    over   composite the *labels* on top, unclipped
    draw   over the data; OSM supplies the single coastline, in DARK_COAST

| figure | stack | claim |
|---|---|---|
| `1_registration` | v1 | the warped render lands on the OSM coastline |
| `2_over_data` | v1 | the style's water is a true alpha hole, so "basemap over data" works |
| `3_coastline` | v1 | Mapbox's custom land buries the Rivière-aux-Outardes; OSM does not |
| `4_label_clip` | v1 | a hard clip crops labels overhanging the sea; the luminance clip does not |
| `5_registration` | v2 | terrain and roads stop on the OSM coastline — the warp is right |
| `6_over_data` | v2 | the production result, straight from `load_basemap` |
| `7_clip` | v2 | the OSM clip *is* the coastline, and it opens the Outardes |
| `8_label_order` | v2 | clip-then-label keeps the names; label-then-clip crops them |

## Run

```bash
# v2, the current stack — needs only our own token
MAPBOX_TOKEN=... .venv/bin/python -m backend.probes.031_mapbox_basemap.probe [--recompute]

# ...plus the superseded v1 stack, which renders a style on someone else's account
OGSL_MAPBOX_TOKEN=... MAPBOX_REFERER=https://nautilo.ca/ \
  .venv/bin/python -m backend.probes.031_mapbox_basemap.probe --legacy
```

The two stacks take **different credentials** — v1 renders an `admin-ogsl` style, v2 renders
ours — so they cannot share `MAPBOX_TOKEN`. Once the borrowed token is revoked, `--legacy`
stops running and the figures it produced remain in `output/` as the record.

Renders are cached on disk by `climatology.utils.basemap` (`~/.cache/ice-clim/basemap/`),
so re-runs are offline; `--recompute` drops the cache and re-fetches.

## Outcome — v1, the OGSL style (2026-07-14, superseded)

**The compositing recipe works.** Four findings carried the design; three of them still hold
in v2, and the fourth is what forced the rewrite.

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

## Outcome — v2, two styles we own (2026-07-14, current)

**The OGSL style could not be cloned — and did not need to be.** A source audit settled it:

| tileset | visibility | maxzoom |
|---|---|---|
| `mapbox.mapbox-streets-v8` | public | 16 |
| `mapbox.mapbox-terrain-v2` | public | 15 |
| `admin-ogsl.land_layer_main_10m` | **private** | 10 |
| `admin-ogsl.7fn1vped` | **private** | 10 |

The style's land comes from two tilesets private to `admin-ogsl`, so a style on another
account cannot reference them — a literal clone yields no land at all. Their `maxzoom=10`
also independently confirms finding 3: the land geometry is baked at z10, so **no zoom could
ever have resolved the Outardes**.

But those two private tilesets are exactly the part we were fighting. The landmask already
overrides them, and everything actually used — hillshade, roads, labels — comes from the two
*public* tilesets. So the four layers reading the private sources were **dropped**, the land
they painted replaced by a flat `background` (`#14151f`), and the symbol layers split into a
second style (`make_styles.py` derives both from the source style; `style/*.json`).

This retires both v1 workarounds and one dependency:

| | v1 (OGSL) | v2 (ours) |
|---|---|---|
| coastline stroke | suppressed via `setfilter` | **absent by construction** |
| land / water | luminance-aware clip (heuristic) | **exact** hard clip to OSM |
| labels | light pixels rescued, halos lost | fetched separately, composited **unclipped**, halos intact |
| token | borrowed, `nautilo.ca`-restricted | ours, no referer |
| billing | charged to OGSL | charged to us |

`8_label_order` measures the gain: the split preserves **6 019** label pixels that a single
flattened render would crop — against the **2 366** the luminance heuristic could rescue, the
difference being the halos.

The order of operations is the whole point, and it is not commutative:

    right:  alpha_over(labels, clip(base, mask))     names intact
    wrong:  clip(alpha_over(labels, base), mask)     names over water cropped

### Cost

Mapbox's free tier is **50 000 Static Images requests/month**. The cache key is
`(region extent, style, size)`, and the extent comes from the region's tier grid — so it is
independent of metric, period and source: **every metric and era for one region shares one
render**. A full sweep of all 9 regions costs 18 requests (2 styles each). Even wiping the
cache and re-fetching every region daily is ~540/month, ~1 % of the free tier. Billing is not
a realistic concern.

## Caveats / open items

- **Sprite substitution.** The derived styles point at the stock `mapbox://sprites/mapbox/
  dark-v11`, since the OGSL style's own sprite is bound to that style. Text labels are
  unaffected; road shields may differ. Not observed to matter at regional zooms.
- **Attribution.** Renders are requested with `attribution=false&logo=false`, so the credit is
  owed in the figure: `_footer` prints `© Mapbox © OpenStreetMap contributors` whenever a
  basemap was drawn.
- **Revoke the borrowed token.** The OGSL token should be dropped from `.env` once `--legacy`
  is no longer needed; the v1 figures in `output/` are the durable record.