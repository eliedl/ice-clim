# Probe 013 — NAD83 / Québec Lambert (32198) Scale-Factor Map (DEC-040)

## Context

`grid_crs` is simultaneously the compute CRS (rasterization, cell size, area)
and the display/archive CRS — the product itself. Its **scale factor k** sets
the gap between nominal grid metres (`res_m`) and true ground metres. To adopt
EPSG:32198 (NAD83 / Québec Lambert) as the single end-product CRS (DEC-040), we
need the distortion across Québec on record, and the contrast with the
zone-dependent UTM (26919) that 32198 replaces.

- **32198** is a Lambert Conformal Conic 2SP (standard parallels 46°N/60°N).
  Conformal ⇒ k is isotropic and depends almost entirely on **latitude**:
  k = 1 on the two parallels, k < 1 between them, k > 1 outside — horizontal
  bands.
- **26919** is Transverse Mercator (UTM 19N), k = 0.9996 on the 69°W central
  meridian, growing off it — **vertical bands**. A single UTM zone cannot serve
  all of Québec (Minganie is UTM-20N territory), which is the DEC-036 rationale.

## Method

- Compute the point scale factor k (`pyproj.Proj.get_factors().meridional_scale`,
  isotropic for a conformal projection) on a lon/lat mesh over Québec
  (lon −80…−57, lat 44…63) for both 32198 and 26919.
- Per region (legacy squares + adaptive, from the production region builder):
  sample k over the region polygon, report max/mean |k−1| and the implied
  ground error |k−1|·res at **25 / 100 / 1000 m**.
- Minganie contrast: max |k−1| under 32198 vs 26919, quantifying why UTM was
  rejected there.
- Render a 2-panel |k−1| map (Lambert horizontal bands vs UTM vertical bands)
  with the standard parallels / central meridian annotated.

No DB access; geometry + pyproj only.

## Expected outcome

- 32198 |k−1| ≲ 0.1–0.2 % (a few parts per thousand) everywhere in Québec;
  ground error at 100 m well under a metre — negligible vs SIGRID-3 source
  resolution. This is the "resolution floor" framing of DEC-040: the projection
  error would bound product resolution only if CIS resolution were infinite.
- 26919 distortion grows without bound east of its zone. **Finding (2026-06-16):**
  at Minganie specifically, 26919's *isotropic point* distortion (~3.9 ppt) is
  **not larger** than 32198's (~7.4 ppt) — both conformal CRSs are modest there.
  The case for 32198 is therefore province-wide **consistency / zone-independence**
  (Minganie is UTM-20N territory; a proper UTM there is 26920, a different CRS
  from the zone-19 regions → multi-zone seams), not smaller point distortion.
  This nuances the DEC-036 phrasing ("26919 would distort") — see DEC-040.

## Run

```bash
.venv/bin/python -m backend.probes.013_qc_lambert_scale_factor.probe
```

Outputs `output/YYYY-MM-DD_HHMMSS{.txt,_scale_factor.png}`.

## Provenance

Feeds DEC-040 (end-product grid CRS = 32198). Relates to DEC-036 (adaptive
regions already on 32198 for the same distortion reason).
