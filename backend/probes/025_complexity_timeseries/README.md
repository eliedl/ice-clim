# Probe 025 — Codebase Complexity Timeseries (DEC-049)

## Context

The 2026-06/07 refactor campaign's success criterion was a **trajectory, not an
invariant**: total LOC shrank ~28 % while the pipeline gained features (landfast metrics,
`ConversionStrategy`, GeoTIFF export, wet-space burn). A test cannot gate a trajectory —
a feature commit legitimately adds lines, so any per-commit LOC assertion either blocks
feature work or rewards code golf (Goodhart). The division of labour is therefore:

- `climatology/tests/test_complexity.py` — **gate** on the local invariant (per-function
  cyclomatic/cognitive ≤ 10), run with the test suite;
- this probe — **monitor** the global trend; re-run at the end of a refactor campaign or
  feature batch and read by a human against the interpretation guide below.

A global-baseline ratchet test (LOC/total-complexity constants bumped on every feature
commit) was considered and rejected: it goes stale without diligent upkeep and taxes
every feature with ledger maintenance (DEC-049).

## Method

Per commit since the campaign origin (2026-06-17, pinned so re-runs extend the same
curve): `git archive` snapshot of the production packages → per-function cyclomatic
(radon), cognitive complexity, arity and tramp-parameter count via the **gate's own
`measure_tree`** (single-sourced — probe curves and test verdicts cannot diverge) →
aggregate LOC (non-blank), function count, totals, means, and maxima. Output: timestamped
CSV + 4-panel PNG under `output/`.

Two orthogonal axes are plotted, because a refactor moves one or the other, rarely both:
**control flow** (panels 1–2, decision points) and **interface coupling** (panel 4, how
much data each signature carries). Arity excludes `self`/`cls` — a receiver is bound by
the call, not supplied by the caller. A *data tramp* (Fowler) is a parameter whose every
use in the body is forwarding it onward; it is measured but deliberately **not gated**,
since unlike a complexity ceiling there is no threshold at which threading a value is
categorically wrong.

```
.venv/bin/python -m backend.probes.025_complexity_timeseries.probe [--since "2026-06-17 00:00"]
```

## Interpretation guide

**No line has a universally good direction — read segment signatures, not slopes.**

- **#functions is granularity, not quality.** Up-while-LOC-flat = *extract-method wave*
  (same logic, smaller units; genuine if total cognitive falls too). Down-while-LOC-crashes
  = *consolidation* (variation moved from code into data tables; the extraction scaffolding
  gets consumed — the intermediate state, not the goal). Both are healthy, in opposite
  phases.
- **Total complexity should not decrease forever.** Essential vs accidental complexity
  (Brooks, *No Silver Bullet* — standard SE reference, not in the project literature
  chain): the domain's branching must live somewhere; refactoring removes only the
  accidental part. The quantity that must fall is **complexity per unit of capability** —
  features landing at near-zero total-complexity cost is the payoff of declarative design.
- **Mean-per-function (CSV only, not plotted) is misleading under refactors**: deleting
  trivial helpers shrinks the denominator faster than the numerator, so the mean *rises*
  while the codebase improves (observed at the declarative `metrics.py` refactor,
  `08a7cf8`). Never a target — this applies to `arity_mean` exactly as to `cc_mean`.
- **Read panel 4 against panels 1–2, not alone.** Interface refactorings (Fowler's
  *Replace Parameter with Query*, narrowing signatures) move panel 4 while leaving
  control flow flat — and can push cyclomatic *up*, since radon charges a base cost per
  function added. Control-flow refactorings (*Extract Method*) do the reverse. The two
  axes disagreeing is the signal, not noise; a commit that moves neither moved no
  structure.

**Standing invariants (any segment, any phase):**

1. **The worst-function line never creeps up.** Flat = untouched, ledgered debt
   (acceptable); rising = a new monster forming.
2. **Totals grow sublinearly with features.** LOC and totals rising in lockstep with a
   flat function count and a creeping max is **code rot / software entropy** — Lehman's
   2nd law of software evolution (complexity increases unless work is done to reduce it;
   standard SE reference, not in the project literature chain). Flat totals are an
   achievement, not a resting state.

**Phase signatures:**

| Phase | LOC | #functions | total complexity | worst function |
|---|---|---|---|---|
| Greenfield (initial build) | up fast | up fast | up ~linearly | rises, then should stabilize |
| Feature development | up | up mildly | up **sublinearly** | flat |
| Refactor: extract-method | flat | **up sharply** | flat or down | steps down if the offender is touched |
| Refactor: consolidation / DRY / declarative | **down sharply** | down | down | flat |
| Dead-code purge | down | down | down | can step down |
| Hardening (tests, edge cases, validation) | up slightly | ~flat | up slightly | flat |
| Optimization | flat / up slightly | flat | often up slightly (fast code is branchier) | **watch it** — perf hotspots breed monsters |
| Code rot / entropy (failure mode) | up | **flat** | up ~linearly with LOC | **creeping up** |

To conclude "on the right path": label what each segment of the window *was meant to be*,
check the curves match its signature, and verify the two invariants. A mismatch (e.g. a
declared refactor week with rising totals) is the red flag.

## Findings (run 2026-07-08, campaign window 2026-06-17 → 2026-07-08, 78 commits)

- LOC 1981 → 1432 (**−27.7 %**) while features grew — the campaign's headline result.
- Total cognitive 145 → 128 (**−11.7 %**); total cyclomatic 212 → 188.
- The window reads as four clean phase signatures: mild feature growth (Jun 17–22) →
  extract-method wave (Jun 23–25: functions 81 → 112, LOC flat, cognitive 147 → 125) →
  consolidation cliff (Jun 30: LOC 2140 → 1390, functions 112 → 84, totals down) →
  features on the clean base (Jul 1–8: landfast metrics + `EventDateDelta` + two
  optimizations for **+1** total cognitive) — the declarative payoff made measurable.
- Worst function flat at cognitive 64 / cyclomatic 18 for the entire window:
  `backend/ingestion/sources.py::ChartSource.discover` — the campaign never touched
  ingestion. Sole `KNOWN_DEBT` entry in the gate; consistent with the optimization-phase
  caveat (it is ingestion's revision-ranking hot path).

## Findings (run 2026-08-26, window 2026-08-17 → 2026-08-26)

Panel 4 was added this window because the control-flow panels reported a *flat line* on a
refactor that had demonstrably reduced coupling — the motivating case for the second axis.

- `3dec88e` (`value_cols`, *Replace Parameter with Query*): cognitive **flat at 204**,
  cyclomatic **+4** — the base cost of two added functions, i.e. the metric penalised the
  improvement. Panel 4 resolves it: params 385 → 383, tramps 135 → 132. Textbook interface
  refactoring: invisible to branch-counting by construction.
- `1bf5c0f` (`ChartSource.discover`, *Extract Method* + loop flattening): the mirror image
  — worst-function cognitive **18 → 9**, total 204 → 199, cyclomatic +1, panel 4 flat.
  The extraction cut along a nesting boundary, where cognitive complexity's progressive
  depth penalty makes the payoff superlinear (18 → 7 + 6, not the ~12 + 6 an additive
  split would give). `discover()` output verified elementwise against `HEAD`, order
  included, over 6 353 archive entries.
- `KNOWN_DEBT` retired: with `discover` under the limit the ledger was empty, so the
  constant and `test_known_debt_only_shrinks` were deleted rather than left as an
  always-passing loop over nothing. The gate is now the single limit check; re-introduce
  the ratchet only if a genuinely un-extractable offender appears.
