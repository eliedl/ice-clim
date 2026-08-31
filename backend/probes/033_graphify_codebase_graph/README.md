# Probe 033 — graphify Codebase Knowledge Graph

## Context

`~/CLAUDE.md` commits this project to **concern-based module placement**: domain algorithms
(`climatology/processing/`), I/O and external interfaces (`climatology/services/`), and
domain-agnostic helpers (`climatology/utils/`) each live in their own package, with
`climatology/pipeline.py` orchestrating on top and `backend/ingestion/` as a separate
vertical. That rule is currently enforced by **discipline only** — nothing measures whether
the boundaries actually hold, and probe 025 (complexity timeseries) measures a different
axis entirely: *how tangled is a function*, not *does a module import across a layer it
shouldn't*.

[graphify](https://github.com/Graphify-Labs/graphify) (PyPI `graphifyy`) makes that axis
measurable at zero API cost. It walks the repo with **tree-sitter**, fully locally, and emits
a knowledge graph — nodes = files / classes / functions / markdown headings, edges =
`imports` · `imports_from` · `calls` · `uses` · `inherits` · `contains`, each tagged
`EXTRACTED` (parsed) / `INFERRED` (heuristic) / `AMBIGUOUS`.

Its own headline features — the "god node" degree ranking and LLM-named community detection
— are **not** what this probe uses. The `source_file` on every node is. Mapping that to the
declared concern turns the graph into an **architecture-conformance check**: every structural
edge that runs *up* the declared layer order is a concern leak, named with file and symbol.

## Hypothesis

**H:** The declared concern boundaries hold — structural dependencies flow downward
(drivers → orchestration → services → processing → utils) — and any violation is a small,
enumerable list of specific edges rather than a diffuse tangle.

**Secondary:** graphify's degree-based "god nodes" and probe 025's cognitive-complexity
ranking identify the *same* debt. (Expected to fail — see Outcome.)

## Scope

**`climatology/` only, minus `tests/`.** `backend/` is excluded because `probes/` are
one-off drivers whose fan-in to the production packages swamps the coupling matrix without
saying anything about the architecture, and `ingestion/` is a separate vertical sharing no
layer order with the climatology stack; `tests/` is excluded for the same driver reason.
Exclusions are applied **at scan time**, so `graph.html` and the report carry identical scope.

Two mechanics are non-obvious and cost a debugging cycle each:

- **The scan is rooted at the repo, and the scope is carved by `--exclude`** — *not* by
  pointing graphify at `climatology/`. graphify resolves `from climatology.processing.x
  import y` by matching the dotted path against corpus file paths; a scan rooted inside the
  package re-keys files as `processing/x.py`, the `climatology.` prefix then matches nothing,
  and **import edges collapse from 137 to 1, silently**. Layer conformance is mostly an
  import-edge question, so that failure mode empties the probe of its finding while still
  producing a plausible-looking report. Measured both ways before choosing.
- **Build products are redirected into this probe's folder** via `GRAPHIFY_OUT` (absolute
  path, read at import time, so it must be set in the child environment at launch). graphify
  otherwise drops `graphify-out/` beside the scanned directory — i.e. at the repo root.

`.graphifyignore` is deliberately unused: graphify reads it only from the scan root and its
ancestors, never from a probe folder, so the exclusions live in `probe.py` instead — version
controlled with the probe and visible in the run line.

## Method

Build the graph locally in two passes — `graphify <root> --code-only --exclude …` for AST
extraction, then `graphify cluster-only …` for communities, `GRAPH_REPORT.md`, and
`graph.html`. `--code-only` is what keeps extraction key-free; it skips the non-code semantic
pass, the only step that hard-fails without an API key.
Then load `graphify-out/graph.json` — a networkx node-link document — and compute four reports:

1. **Layer violations** — the actionable list. `LAYER_RANK` in `probe.py` encodes the
   declared order; an edge whose target sits at a *lower* rank than its source is printed
   with relation, confidence, and both endpoints.
2. **Cross-concern matrix** — all structural edges between differing concerns, legal ones
   included, to show the shape of coupling.
3. **Doc / code connectivity** — `file_type` crosstab, testing whether the markdown
   corpus (DECISIONS/LITERATURE/probe READMEs) joins the code graph.
4. **Degree vs cognitive complexity** — the two hub rankings side by side, with the
   complexity side single-sourced from the probe-025 / test-gate `measure_tree` so the
   probe and the gate cannot diverge.

`contains` (file→symbol) and `rationale_for` (docstring→symbol) edges are excluded from
the structural set: they are artifacts of how graphify represents containment, not coupling.

A scope guard in `_concern` raises on any node outside `climatology/` rather than bucketing
it into a catch-all — if a future graphify release changes how `--exclude` is honoured, the
probe fails loudly instead of quietly reporting on the wrong corpus.

### Communities: assignment, then naming

**Assignment** (`cluster.py`) is modularity optimization on the undirected graph — Leiden via
graspologic if installed, else **networkx Louvain, `seed=42`** (our case), then four
deterministic post-passes: isolates become singletons; degree-0 nodes and any excluded super
-hubs are reattached by majority vote of their neighbours' communities; communities over 25 %
of the graph, or larger than 50 nodes with cohesion < 0.05, are re-split; finally communities
are re-indexed by size descending with a sorted-member tiebreak, so identical groupings always
get identical integer ids. Assignment is therefore reproducible, and note it is **purely
topological** — file paths and package boundaries play no part.

**Naming** then labels each community after its **highest-degree member**
(`label_communities_by_hub`). Degree is measured on the *full* graph, so edges to other
communities count toward winning the name; ties break by node id ascending; a trailing `()` is
stripped. This is the default no-backend labeler, and it only runs when `--no-label` is
absent — that flag suppresses the free hub pass along with the LLM pass, which is more than it
advertises and cost this probe a run of 25 unusable `Community N` labels. With no API key
graphify prints `no LLM backend configured; keeping Community N placeholders` and leaves the
hub labels standing; the message is wrong, the behaviour is right. A configured provider key
would override these names and ship the corpus to that provider.

Naming is degree-based, which the Outcome below argues is the wrong *debt* ranking — no
contradiction: degree picks a representative member well and ranks technical debt badly.

```
python3 -m venv ~/.local/venvs/graphify
~/.local/venvs/graphify/bin/pip install 'graphifyy==0.9.50'

.venv/bin/python -m backend.probes.033_graphify_codebase_graph.probe [--skip-build]
```

The version is **pinned**: graphify is pre-1.0 with ~250 releases, so the JSON schema is not
stable. It lives in a dedicated venv (override with `GRAPHIFY_BIN`) rather than the project
`.venv`, to keep a fast-moving pre-1.0 dependency out of the environment the climatology
pipeline runs in. The `/graphify` assistant skill (`graphify install`) is deliberately **not**
registered — this probe uses the CLI only, so the artifact stays self-contained.

Output: timestamped `.txt` report + a copy of the interactive `graph.html` under `output/`
(both gitignored, per the project convention that probe READMEs carry the findings).
`graphify-out/` beside them holds graphify's own build products and SHA256 cache, so a re-run
only re-parses changed files; it is gitignored and safe to delete.

Positions in `graph.html` carry no information: the layout is an unseeded ForceAtlas2 quench
(200 iterations, then physics off), so it differs on every page load, and community color has
no attractive term in the physics. Read topology from `graph.json`, not from the picture.

## Outcome (2026-08-31, commit `1bf5c0f`, `output/2026-08-31_134557.txt`)

**Corpus:** 19 files → 461 nodes · 947 edges · 403 structural · 25 communities.
**Extraction quality: 96 % `EXTRACTED`, 4 % `INFERRED`, 0 % `AMBIGUOUS`** — the leak list
below is parsed fact, not heuristic.

The narrowed scope changed the corpus by a factor of three (1551 → 461 nodes) but **left
every architectural conclusion identical** — same 11 violating edges, same 4 leaks, same
0/12 hub disagreement. The `backend/` fan-in was noise in the coupling matrix, not signal.

### H confirmed — 11 violating edges, resolving to 4 named leaks

| # | Leak | Verdict |
|---|---|---|
| 1 | `processing/metrics.py` → `services/temporal.py::filter_admissible_days` | **Misfiled module, not a leak.** `services/temporal.py` contains *no I/O whatsoever* — `day_of_season`, `winter_season`, `attach_season_calendar`, `filter_admissible_days` are pure pandas/numpy season-calendar algorithms. It is a **domain module sitting in the I/O package**. The graph flags the import because the file is in the wrong place. → move `temporal.py` to `climatology/processing/`. |
| 2 | `utils/polygons.py` → `services/sources.py::LAND_MASK_PATH`, then `gpd.read_file(...)` at `polygons.py:39` | **Real leak.** A "domain-agnostic helper" reaching into a services-owned path constant and doing file I/O. The sharpest of the four. |
| 3 | `utils/{polygons,basemap}.py` → `processing/rasterize.py::GRID_CRS` | **Real but trivial.** A CRS constant is domain-agnostic; it is in the wrong package, not used wrongly. → move `GRID_CRS` down to `utils/`. |
| 4 | `services/{plot,export}.py` → `pipeline.py::{RunContext, TierProduct}` | **Accept by design.** `RunContext` is the pure-dataclass context object the convention prescribes; importing it is what makes downstream signatures narrow. Worth noting only because it makes `pipeline.py` a bidirectional hub (degree 56). |

Everything else flows downward as declared. The coupling matrix is now dominated by
`clim-core → services` (33), `drivers → services` (32, i.e. `scripts/`), `clim-core →
processing` (19) and `services → processing` (18) — the orchestrator and the batch drivers
consuming the production packages, exactly the intended direction.

### Secondary hypothesis rejected — degree and complexity are disjoint

**0 of 12** symbols overlap between the two top-12 rankings, and the gap is not marginal:
degree runs 20–60 edges across the board while the *entire* cognitive ranking now fits in
3–9, the whole package sitting under the gate's limit of 10. Degree is dominated by shared
semantic types and plotting modules (`plot.py` 60, `pipeline.py` 47, `export.py` 41,
`Tier` 31); the cognitive ranking is led by `utils/basemap.py::fetch_style_png` (9), which
does not appear in the degree list at all.

This is not a defect in either measure — it is a **finding about what "god node" means here**.
High degree on `Tier` / `RunContext` / `Grid` is the *intended* outcome of the project's
"semantic types across call chains" convention: a widely-shared, deliberately-designed type
looks identical to a god object under a pure degree metric. **Do not read graphify's god-node
list as a debt ranking on this codebase.** The two probes measure orthogonal debts — 033 is
*where does coupling cross a boundary*, 025 is *which function is tangled*.

The disjointness held under the whole-repo run too, where the comparison had a sharper test
available. `ChartSource.discover` (`backend/ingestion/`, now out of scope) was the standing
worst-function debt probe 025 tracked flat at cognitive **64** for two months, paid down in
`a528e43` (extract-method, 64 → 18) and `1bf5c0f` (`_clean_charts` split + `itertools.product`
replacing a nested loop, 18 → **7**). Its *degree* never once entered graphify's top 12 across
that entire trajectory. A metric blind to the codebase's single largest complexity debt, from
64 down to 7, is not measuring complexity — and that conclusion is what licenses reading the
two probes as orthogonal rather than redundant.

## Limits

- **Nothing doc-side is captured.** Under `--code-only` the corpus is 269 code nodes and 192
  `rationale` nodes (docstring→its own function); markdown is not ingested at all. This is not
  much of a loss: the whole-repo run *did* ingest `docs/` and produced **zero** doc↔code edges
  — without an LLM backend the markdown extractor builds a heading tree and nothing more, so
  community hubs like "Scientific Decision Log" were heading structure, not semantic linkage.
  Either way this project's central provenance chain — DEC-0NN entries cross-referencing code
  paths and probe dirs — is **not** in the graph. Capturing it needs semantic extraction
  (`GEMINI_API_KEY`/`GOOGLE_API_KEY`), which would send source and docs to a third party — not
  done, and a decision to log before it is.
- **The graph is undirected** (`"directed": false` in `graph.json`). Direction survives only
  in each edge's `source`/`target` fields, which this probe reads directly; graphify's own
  clustering and degree metrics discard it. Any layering conclusion must come from the edge
  list, never from the built-in community/god-node views.
- **The scope cut is by construction, so `backend/` conclusions are simply unavailable** —
  including the `initdb/*.sql` DDL ↔ `_KEEP` whitelist sync that `CLAUDE.md` flags as a manual
  hazard. That one needs `tree_sitter_sql` anyway (`pip install 'graphifyy[sql]'`; the
  whole-repo run warned the `.sql` files contributed nothing without it). If the ingestion
  vertical ever wants the same conformance treatment it should be a **separate probe with its
  own layer order**, not a widening of this one — the two stacks share no ranking.
- **`INFERRED` edges (4 %) are heuristic** on dynamically-dispatched Python. Here they only
  reinforced conclusions already carried by `EXTRACTED` imports; treat them as corroboration,
  never as sole evidence. Note the two `uses` violations would be the *only* violations if the
  import edges were ever lost again — see the scan-root trap under Scope.
- **Snapshot, not gate.** This probe reports; it does not fail a build. Whether the layer
  order deserves a `test_layering.py` assertion — the architectural analogue of
  `test_complexity.py` — is a **[NEEDS REVIEW]** decision, not something to adopt implicitly.

## Status

**complete** 2026-08-31 — first run at `1bf5c0f`, scoped to `climatology/` minus `tests/`.
Hypothesis confirmed (11 edges → 4 named leaks, 3 actionable); secondary hypothesis rejected
(degree ⊥ complexity, 0/12 overlap). Re-run after a refactor campaign or when adding a
package, alongside probe 025.
