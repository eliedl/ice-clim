# Probe 020 — Landfast CT=1.0 Proxy Validation (median-level)

## Hypothesis

Probe 019 found landfast ⟺ `CT=1.0` with ~99% two-way agreement **per polygon**,
but the ~0.7–1.0% compact-drift contamination is a per-polygon count and only an
**upper bound** on the climatological error. The climatology is
median-then-threshold (DEC-025/027): a cell registers at median CT=1.0 only when
>50% of seasons are compact there, so transient compact drift should be
suppressed. Hypothesis: the CT=1.0 proxy reproduces a direct `FA='08'` fast-ice
climatology to within a negligible **median-level** error.

## Method

Two median-then-threshold climatologies on the same sept-îles 2011–2020 grid,
cell-diffed (the probe-010 pattern, internal ground truth):

- **proxy** — `CT_CONVERSION`, `ThresholdCount(1.0, ge)` / `EventDate(1.0, …)`:
  median CT ≥ 1.0 (compact).
- **direct** — landfast indicator `1.0 if FA='08' else 0.0`,
  `ThresholdCount(0.5, ge)` / `EventDate(0.5, …)`: fast ice in >50% of seasons.

The direct conversion is defined locally in the probe (not yet adopted into
`units_conversion_maps.py` — that awaited this validation). Both run through the
current pipeline (`RunContext` + `FetchResult.prepare` + `_compute_tiers`), so the
diff isolates only the proxy-vs-indicator difference. Metrics compared: duration,
freeze-up, breakup.

## Run

```bash
.venv/bin/python backend/probes/020_landfast_proxy_validation/probe.py
# other region/period:
... probe.py --region mingan --period 2011-2020
```

## Outcome (2026-07-01, output/2026-07-01_173448_sept-iles_2011-2020.txt)

**The CT=1.0 proxy is validated** — at the median level it is indistinguishable
from the direct `FA='08'` fast-ice climatology:

| metric | exact agreement (Δ=0) | max \|Δ\| | presence mismatch |
|---|---|---|---|
| freeze-up | **100.00%** (62 624 cells) | 0 d | 0 / 0 |
| duration | **99.15%** (583 587 / 588 603) | 2 d | 0 / 0 |
| breakup | **97.13%** (60 825 / 62 624) | 2 d | 0 / 0 |

- **Presence mismatch is 0/0 for every metric** — the proxy and the direct
  indicator mark fast ice at the **exact same cells**. The per-polygon ~1%
  compact-drift contamination (probe 019) produces **zero** false-positive cells
  at the climatology level: median-then-threshold fully suppresses it, confirming
  the hypothesis.
- The residual ≤2-day deltas (duration: proxy 1–2 d shorter for ~5 k cells;
  breakup: proxy ~1 d earlier for ~1.8 k cells) are one-HD quantization at the
  season edges, not contamination — freeze-up is bit-exact.

### Implication

A fast-ice climatology is the existing `EventDate` / `ThresholdCount` kernels on
`CT_CONVERSION` at **threshold 1.0** — no new compute kernel, no new conversion,
no measurable accuracy cost vs. gating on `FA='08'`. The landfast `MetricSpec`s
(probe 019's table) can be added to `METRICS` as-is.

### Follow-up

- **Probe 021** — external validation against the published CIS 1991–2020 EC
  fast-ice freeze-up normals (`fifup.shp`), same diff pattern.