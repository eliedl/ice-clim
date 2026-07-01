# Probe 021 — CT=1.0 Proxy vs CIS Fast-Ice Freeze-Up Normals

## Context

Probe 019 established landfast ⟺ `CT=1.0` (per polygon); probe 020 validated it
**internally** at the median level (proxy vs a direct `FA='08'` indicator: 100%
exact freeze-up agreement, 0 presence mismatch). This probe is the **external**
validation: does the CT=1.0 proxy fast-ice freeze-up climatology reproduce the
**published CIS 1991–2020 EC fast-ice freeze-up normals** (`fifup.shp`)? Same
diff pattern as probe 010 (which validated the regular freeze-up against
`freeze.shp`).

## Method

1. **Ours** — `EventDate(1.0, "first_above")` on `CT_CONVERSION`: the first HD
   whose median CT reaches 1.0 (compact ≈ fast ice), `sgrdr` winters 1991–2020,
   sept-îles grid, through the current pipeline. Cached to `output/ours_values.npy`
   (`--recompute` to rebuild).
2. **CIS** — `fifup.shp`, the `fifup` column: an MMDD fast-ice-freeze-up week per
   polygon (`'0'` = climate-normals landmask / no fast ice, excluded; the weekly
   `-1/0/1` columns are supporting data, unused). Reprojected to the grid CRS
   (EPSG:32198), each MMDD mapped to the same Sep-1-anchored day-of-season ordinal
   and burned onto the grid.
3. **Difference** — `ours − CIS` in days (positive = ours later); coverage
   mismatch, signed distribution, agreement bands (±half-week/±1/±2 weeks), maps
   + histogram.

**Caveat (inherited from probe 010):** a CIS class label is the HD *week* the
normal field crossed; the within-week placement convention (start vs mid-week) is
undocumented, so a constant ~±3.5 d offset in the median is a labelling
convention, not a real discrepancy.

## Run

```bash
.venv/bin/python backend/probes/021_landfast_vs_cis_fifup/probe.py [--recompute]
```

Outputs `output/YYYY-MM-DD_HHMMSS{.txt,_difference.png}`; proxy raster cached at
`output/ours_values.npy`.

## Outcome (2026-07-01, output/2026-07-01_173843.txt)

**The CT=1.0 proxy reproduces the published CIS fast-ice freeze-up normals to
within the CIS weekly quantization** — external validation passed.

| metric | value |
|---|---|
| cells defined in both | 76 738 |
| proxy-only / CIS-only | 75 / 27 (coverage mismatch ~0.1%) |
| signed diff (proxy − CIS) | **median +0.0 d, mean −0.0 d, std 0.8 d** (p05…p95 all +0.0) |
| \|diff\| ≤ 3.5 d (half-week) | **99.1%** |
| \|diff\| ≤ 7 d (one week) | 99.9% |
| \|diff\| ≤ 14 d | 100.0% |
| value range (both) | Jan 01 – Feb 26 (identical) |

- The difference is **zero-centred with sub-day spread** (std 0.8 d) and 99.1% of
  cells agree to within half a CIS week — i.e. at or below the CIS labelling
  granularity. There is **no systematic bias** (median and every reported
  percentile are 0), so the proxy is not early/late relative to CIS.
- Coverage mismatch is negligible: 75 cells where our compact-freeze occurs but
  CIS carries no fast-ice normal, and 27 where CIS has fast ice our proxy never
  reaches 1.0 — a fringe of ~0.13% of the 76 k common cells.

### Conclusion

Together with the internal validation (probe 020: 100% exact freeze-up vs a
direct `FA='08'` indicator), this **externally confirms** that
`EventDate(1.0, "first_above")` on `CT_CONVERSION` is a sound fast-ice freeze-up
climatology — it matches both the direct landfast indicator *and* the
authoritative CIS 1991–2020 normals. The landfast `MetricSpec`s (probe 019) can
be committed to `METRICS` at threshold 1.0 with confidence.