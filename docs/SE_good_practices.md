Great question to ask while looking at run — it's the textbook example of an orchestrator (a.k.a. the "imperative shell"), and there's a well-defined shape for it. Here's the standard, the principles behind it, then applied to your actual run.

The canonical shape
An orchestrator should read like a table of contents — a flat sequence of named stages, each delegating the actual work:


def run(config):
    ctx     = resolve(config)        # 1. gather + validate inputs   (fail fast)
    data    = fetch(ctx)             # 2. I/O in
    results = compute(data, ctx)     # 3. pure transformation        (functional core)
    emit(results, ctx)               # 4. I/O out                    (persist / render)
If run reads top-to-bottom like that — four to seven named steps, each one verb-phrase clear — it's well-formed. The moment a line computes rather than delegates, it's drifting.

The principles that produce that shape
Principle	What it buys	The one-line test
Functional core, imperative shell (Bernhardt)	testability + debugging	Is the pure computation separated from I/O (DB, files, plotting)?
Single Level of Abstraction (SLAP)	readability	Is every line in run at the same altitude?
Compose, don't compute	maintainability	Does run contain any literal/loop/dict logic, or only calls?
Fail fast, guard clauses up front	debugging	Are preconditions validated before the expensive work?
Separate iteration from per-item work	scalability	Is the loop body a named function the loop just calls?
Explicit dependencies (injection)	testability + config	Does it reach for module globals, or receive what it needs?
Idempotent / checkpointed stages	scalability	Can a re-run skip already-done work?
The deepest one is functional core / imperative shell. Pure compute (no side effects) is trivially unit-testable and gives clean stack traces; I/O is pushed to a thin outer layer. That single split is what most improves all three of your goals at once.

Applied to your run
Your run is already close — it has the right spine (resolve → fetch → validate → loop → render). The SLAP violations are concentrated in two places:

1. The per-tier loop body (main.py:125-163) spans four altitudes in one block — grid construction, masking, pure compute, manifest-dict assembly, archival I/O, GeoTIFF tag logic, file writes. That's the biggest issue. The fix is extract the loop body into a named function, separating the pure part from the emit part:


def run(...):
    ctx = _resolve(metric_slug, region, source_slug, period)   # metric/source/region/labels
    df  = _fetch(ctx)                                           # sql + load_polygons
    _validate(df, ctx)                                          # empty + HD guards (fail fast)

    products = [_compute_tier(df, tier, ctx) for tier in ctx.spec.tiers]   # functional core
    _emit(products, ctx, geotiff=geotiff)                                  # archive + geotiff + plot
where _compute_tier returns a small TierProduct value object (values, bounds, transform, manifest) and does no I/O — so you can unit-test "did tier X compute correctly?" without touching disk. _emit is the imperative shell: archival, GeoTIFF, composite plot.

2. Data assembly inline — the manifest dict (146-152) and the tags dict (157-160) are construction logic at the wrong altitude. Each becomes a _build_manifest(...) / _geotiff_tags(...) helper, so the loop reads as intent, not plumbing.

The payoffs map exactly to what you asked:

Scalability — once _compute_tier is a pure function of (df, tier, ctx), the [... for tier in tiers] becomes a trivially parallelizable map (ProcessPoolExecutor) with zero logic change. You can't parallelize the current inline loop because its body is tangled with shared I/O.
Maintainability — adding a new output format touches only _emit; a new metric touches only the core; the orchestrator never changes.
Debugging — a failure now surfaces as _compute_tier vs _emit in the traceback (which stage broke), each stage is independently testable, and you can log/time per stage at the boundaries.
