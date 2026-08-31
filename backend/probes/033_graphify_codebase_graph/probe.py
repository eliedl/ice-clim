"""Probe 033 — graphify codebase knowledge graph: do the declared concern boundaries hold?

`graphify` (PyPI `graphifyy`) parses a repo with tree-sitter and emits an undirected
knowledge graph — nodes = files/classes/functions/doc headings, edges = imports/calls/
contains, each tagged EXTRACTED | INFERRED | AMBIGUOUS. It ships a "god nodes" degree
ranking and community detection out of the box.

Those built-ins are not the measurement. The `climatology/` package declares a *concern architecture*
(`processing/` domain algorithms · `services/` I/O · `utils/` agnostic helpers), which makes
the graph falsifiable: every structural edge that runs *up* the declared layer order is a
concern leak, named with file and symbol. That is what this probe computes — an
architecture-conformance check, with graphify as the parser.

Scope is `climatology/` minus `tests/`. `backend/` is excluded because `probes/` are one-off
drivers whose fan-in to the production packages swamps the coupling matrix without saying
anything about the architecture, and `ingestion/` is a separate vertical that shares no layer
order with the climatology stack; `tests/` is excluded for the same driver reason. The
exclusions are applied at scan time, so `graph.html` and the report carry identical scope.

Four reports:
  1. layer violations — the actionable list, edge by edge with relation and confidence;
  2. the same leaks rolled up by concern pair, to show which boundary is worst;
  3. graph composition — the standing check that docstring nodes really were filtered out;
  4. degree vs cognitive complexity — the two hub rankings, single-sourced against the
     probe-025 gate's `measure_tree`. They are expected to *disagree*: degree rewards
     shared semantic types (`Tier`, `RunContext`), which this codebase creates on purpose.

Legal cross-concern edges are deliberately not reported: they are the intended downward flow,
and counting them buried the handful of leaks that are the actual finding.

Read-only on the repo: graphify's build products are redirected into this probe's own
`graphify-out/` (gitignored) rather than dropped beside the scanned package.

Run:
    .venv/bin/python -m backend.probes.033_graphify_codebase_graph.probe [--skip-build]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from climatology.tests.test_complexity import REPO_ROOT, measure_tree

OUTPUT_DIR = Path(__file__).parent / "output"
SCOPE_PREFIX = "climatology/"
# Scope is carved by exclusion from the repo root, NOT by scanning climatology/ directly:
# graphify resolves `from climatology.x import y` by matching the dotted path against corpus
# file paths, so a scan rooted inside the package re-keys files as `x/...`, the `climatology.`
# prefix matches nothing, and ~137 import edges vanish silently (1 survived, vs 137 here).
# Excluding at scan time rather than filtering afterwards keeps graph.html and the report
# on identical scope. It travels as an argument because graphify reads .graphifyignore only
# from the scan root and its ancestors — never from this probe's folder.
SCAN_ROOT = REPO_ROOT
SCAN_EXCLUDES = ("backend/", "climatology/tests/")
# graphify defaults to <scan root>/graphify-out; GRAPHIFY_OUT overrides it with an absolute
# path and is read at import time, so it must be set in the child's environment at launch.
GRAPH_OUT = Path(__file__).parent / "graphify-out"
DEFAULT_BIN = Path.home() / ".local/venvs/graphify/bin/graphify"

# Pinned: graphify is pre-1.0 with ~250 releases, so the JSON schema is not stable.
PINNED_VERSION = "0.9.50"

# Declared dependency direction, low rank = high layer. An edge is a violation iff it
# points at a *lower* rank number than its source, i.e. runs up the stack.
LAYER_RANK = {"scripts": 0, "clim-core": 1, "processing": 2, "services": 3, "utils": 4}

# Paths are relative to the scan root (the repo). Longest prefix wins; anything else under
# climatology/ is the orchestration layer (pipeline.py, main.py).
CONCERN_PREFIXES = (
    ("climatology/processing", "processing"),
    ("climatology/services", "services"),
    ("climatology/utils", "utils"),
    ("climatology/scripts", "scripts"),
)

# Relations that carry a real code dependency; `contains` (file→symbol) and
# `rationale_for` (docstring→symbol) are structure of the extraction, not coupling.
STRUCTURAL = {"calls", "imports", "imports_from", "uses", "inherits", "method", "indirect_call"}

TOP_HUBS = 12


def _build(binary: Path) -> None:
    """Extract then cluster the scoped code graph into graphify-out/ (local AST, no LLM, no API key)."""
    if not binary.exists():
        sys.exit(f"graphify not found at {binary}\n"
                 f"  python3 -m venv {binary.parents[1]}\n"
                 f"  {binary.parents[0]}/pip install 'graphifyy=={PINNED_VERSION}'\n"
                 f"or set GRAPHIFY_BIN to an existing install.")
    env = {**os.environ, "GRAPHIFY_OUT": str(GRAPH_OUT)}
    excludes = [arg for pattern in SCAN_EXCLUDES for arg in ("--exclude", pattern)]
    # --code-only keeps extraction key-free. Clustering is a separate command, left to name
    # communities after their highest-degree member (graphify's deterministic hub labeler);
    # --no-label is deliberately NOT passed, since it would suppress that pass too and leave
    # bare "Community N".
    subprocess.run([str(binary), str(SCAN_ROOT), "--code-only", *excludes], check=True, env=env)
    _drop_rationale_nodes()
    # Clustering runs on the filtered graph, so communities, hub names and graph.html all
    # describe structure alone rather than which symbols happen to carry a docstring.
    subprocess.run([str(binary), "cluster-only", str(GRAPH_OUT.parent)], check=True, env=env)


def _drop_rationale_nodes() -> None:
    """Strip docstring nodes and their rationale_for edges from graph.json, in place."""
    path = GRAPH_OUT / "graph.json"
    graph = json.loads(path.read_text())
    # Docstrings are pure leaves: one outgoing rationale_for to the symbol they document and
    # no other edge, so they carry no coupling — but they are ~40 % of the nodes, they add +1
    # degree to every documented symbol (skewing the hub naming and god-node ranking toward
    # documentation), and they render as confetti with no positional meaning.
    dropped = {node["id"] for node in graph["nodes"] if node.get("file_type") == "rationale"}
    graph["nodes"] = [node for node in graph["nodes"] if node["id"] not in dropped]
    kept = [link for link in graph["links"]
            if link["source"] not in dropped and link["target"] not in dropped]
    orphaned = len(graph["links"]) - len(kept) - sum(
        1 for link in graph["links"] if link["relation"] == "rationale_for")
    if orphaned:
        raise ValueError(f"{orphaned} non-rationale_for edges touched a rationale node")
    removed_edges = len(graph["links"]) - len(kept)
    graph["links"] = kept
    path.write_text(json.dumps(graph))
    print(f"filtered: -{len(dropped)} rationale nodes, -{removed_edges} rationale_for edges")


def _load_graph() -> tuple[dict[str, dict], list[dict]]:
    """(nodes by id, links) from graphify-out/graph.json."""
    graph = json.loads((GRAPH_OUT / "graph.json").read_text())
    return {node["id"]: node for node in graph["nodes"]}, graph["links"]


def _concern(source_file: str | None) -> str:
    """Map a node's source file to its declared concern."""
    if not source_file:
        return "external"
    for prefix, concern in CONCERN_PREFIXES:
        if source_file.startswith(prefix):
            return concern
    if source_file.startswith(SCOPE_PREFIX):
        return "clim-core"
    raise ValueError(f"out-of-scope node survived the scan exclusions: {source_file}")


def _structural_edges(nodes: dict[str, dict], links: list[dict]) -> list[tuple]:
    """(relation, confidence, source node, target node) for every code-dependency edge."""
    edges = []
    for link in links:
        if link["relation"] not in STRUCTURAL:
            continue
        source, target = nodes.get(link["source"]), nodes.get(link["target"])
        if source and target:
            edges.append((link["relation"], link["confidence"], source, target))
    return edges


def _describe(node: dict) -> str:
    return f"{node.get('source_file') or '<external>'}::{node.get('label')}"


def _is_upward(source: dict, target: dict) -> bool:
    """True when a structural edge runs up the declared layer order — i.e. is a concern leak."""
    ranks = (LAYER_RANK.get(_concern(source.get("source_file"))),
             LAYER_RANK.get(_concern(target.get("source_file"))))
    return None not in ranks and ranks[1] < ranks[0]


def _layer_violations(edges: list[tuple]) -> list[str]:
    """Every structural edge running up the declared layer order, most specific first."""
    return sorted(f"  {_describe(source)}\n"
                  f"      --{relation} ({confidence})-->  {_describe(target)}"
                  for relation, confidence, source, target in edges
                  if _is_upward(source, target))


def _illegal_by_concern_pair(edges: list[tuple]) -> list[str]:
    """Leaking edges grouped by the concern pair they violate, worst pair first."""
    grouped = collections.defaultdict(set)
    for _, _, source, target in edges:
        if _is_upward(source, target):
            pair = _concern(source.get("source_file")), _concern(target.get("source_file"))
            grouped[pair].add((_describe(source), _describe(target)))
    lines = []
    for (origin, destination), endpoints in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {len(endpoints):4d}  {origin} -> {destination}")
        lines += [f"          {source}  ->  {target}" for source, target in sorted(endpoints)]
    return lines or ["  none"]


def _composition(nodes: dict[str, dict], links: list[dict]) -> list[str]:
    """Node file_types and edge relations — the standing check that the graph is structure only."""
    types = collections.Counter(node.get("file_type") for node in nodes.values())
    relations = collections.Counter(link["relation"] for link in links)
    return ([f"  {count:5d} nodes  file_type={file_type}" for file_type, count in types.most_common()]
            + [f"  {count:5d} edges  {relation}" for relation, count in relations.most_common()])


def _degree_ranking(nodes: dict[str, dict], links: list[dict]) -> list[tuple[dict, int]]:
    """Nodes by edge count — graphify's own 'god node' notion."""
    degree = collections.Counter()
    for link in links:
        degree[link["source"]] += 1
        degree[link["target"]] += 1
    ranked = [(nodes[node_id], count) for node_id, count in degree.most_common() if node_id in nodes]
    return ranked[:TOP_HUBS]


def _complexity_ranking() -> list[tuple[str, int]]:
    """In-scope functions by cognitive complexity, from the probe-025 / test gate measurement."""
    # measure_tree spans PACKAGES (climatology + backend/ingestion) and already drops tests/
    # via EXCLUDE_PARTS; the prefix filter is what holds it to this probe's scope.
    measures = {key: m for key, m in measure_tree(REPO_ROOT).items()
                if key.startswith(SCOPE_PREFIX)}
    ranked = sorted(measures.items(), key=lambda item: -item[1]["cognitive"])
    return [(key, measure["cognitive"]) for key, measure in ranked[:TOP_HUBS]]


def _symbol(key_or_label: str) -> str:
    """Bare symbol name from either a measure key (`path::Class.method`) or a graphify label (`.method()`)."""
    tail = key_or_label.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    return tail.removesuffix("()").strip(".").lower()


def _report(nodes: dict[str, dict], links: list[dict]) -> str:
    """Assemble the full probe report."""
    edges = _structural_edges(nodes, links)
    violations = _layer_violations(edges)
    degree, complexity = _degree_ranking(nodes, links), _complexity_ranking()
    overlap = {_symbol(k) for k, _ in complexity} & {_symbol(n.get("label", "")) for n, _ in degree}

    out = [f"Probe 033 — graphify codebase graph  ({datetime.now():%Y-%m-%d %H:%M:%S})",
           f"graphify {PINNED_VERSION} · commit {json.loads((GRAPH_OUT / 'graph.json').read_text())['built_at_commit'][:8]}",
           f"{len(nodes)} nodes · {len(links)} edges · {len(edges)} structural",
           "",
           f"1. LAYER VIOLATIONS  ({len(violations)} edges run up the declared order "
           f"{' > '.join(LAYER_RANK)})", ""]
    out += violations or ["  none"]

    out += ["", "", "2. ILLEGAL EDGES BY CONCERN PAIR  (distinct endpoint pairs)", ""]
    out += _illegal_by_concern_pair(edges)

    out += ["", "", "3. GRAPH COMPOSITION  (docstring nodes filtered out before clustering)", ""]
    out += _composition(nodes, links)

    out += ["", "", f"4. HUB RANKINGS — degree vs cognitive complexity "
                    f"({len(overlap)}/{TOP_HUBS} symbols in common)", "",
            f"  {'graphify degree':<44}   cognitive complexity", ""]
    for (node, count), (key, cognitive) in zip(degree, complexity):
        out.append(f"  {node.get('label', '?')[:32]:<34}{count:4d}   {key[-44:]:<46}{cognitive:3d}")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse the existing graphify-out/graph.json instead of re-extracting")
    args = parser.parse_args()

    if not args.skip_build:
        _build(Path(os.environ.get("GRAPHIFY_BIN", DEFAULT_BIN)))

    report = _report(*_load_graph())
    print(report)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    text_path = OUTPUT_DIR / f"{stamp}.txt"
    text_path.write_text(report)
    html_path = shutil.copy(GRAPH_OUT / "graph.html", OUTPUT_DIR / f"{stamp}_graph.html")
    print(f"saved: {text_path}\nsaved: {html_path}")


if __name__ == "__main__":
    main()
