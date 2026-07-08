"""Complexity gate — fails when a function exceeds the guardrail or known debt grows."""
import ast
import sys
from pathlib import Path

from cognitive_complexity.api import get_cognitive_complexity
from radon.complexity import cc_visit

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("climatology", "backend/ingestion")
EXCLUDE_PARTS = {"tests", "__pycache__"}

CYCLOMATIC_LIMIT = 10
COGNITIVE_LIMIT = 10

# Ratchet ledger: functions exceeding the limits before the gate existed.
# Entries may only shrink; once within limits, the entry must be removed.
KNOWN_DEBT = {
    "backend/ingestion/sources.py::ChartSource.discover": {"cyclomatic": 18, "cognitive": 64},
}


def _function_nodes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """Yield (qualified_name, node) for every function/method, including nested ones."""
    found = []

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((".".join(stack + [child.name]), child))
                walk(child, stack + [child.name])
            elif isinstance(child, ast.ClassDef):
                walk(child, stack + [child.name])
            else:
                walk(child, stack)

    walk(tree, [])
    return found


def _cyclomatic_by_line(source: str) -> dict[int, int]:
    """Map def-statement line number to radon cyclomatic complexity, classes flattened to methods."""
    by_line = {}

    def flatten(blocks):
        for block in blocks:
            if hasattr(block, "methods"):
                flatten(block.methods)
                flatten(getattr(block, "inner_classes", []))
            else:
                by_line[block.lineno] = block.complexity
                flatten(getattr(block, "closures", []))

    flatten(cc_visit(source))
    return by_line


def measure_tree(root: Path) -> dict[str, dict]:
    """Measure both complexities for every production function under root, keyed by path::qualname."""
    measures = {}
    for package in PACKAGES:
        if not (root / package).exists():
            continue
        for file in sorted((root / package).rglob("*.py")):
            if EXCLUDE_PARTS & set(file.parts):
                continue
            source = file.read_text()
            cyclomatic = _cyclomatic_by_line(source)
            for qualname, node in _function_nodes(ast.parse(source)):
                key = f"{file.relative_to(root)}::{qualname}"
                measures[key] = {
                    "line": node.lineno,
                    "cyclomatic": cyclomatic.get(node.lineno, 1),
                    "cognitive": get_cognitive_complexity(node),
                }
    return measures


def measure_repo() -> dict[str, dict]:
    """Measure the working tree."""
    return measure_tree(REPO_ROOT)


def _over_limit(measure: dict) -> bool:
    return measure["cyclomatic"] > CYCLOMATIC_LIMIT or measure["cognitive"] > COGNITIVE_LIMIT


def _describe(key: str, measure: dict) -> str:
    return (f"  {key} (line {measure['line']}): "
            f"cyclomatic={measure['cyclomatic']}/{CYCLOMATIC_LIMIT}, "
            f"cognitive={measure['cognitive']}/{COGNITIVE_LIMIT}")


def test_functions_within_complexity_limits():
    """No function outside the debt ledger may exceed the complexity limits."""
    offenders = [
        _describe(key, measure)
        for key, measure in measure_repo().items()
        if key not in KNOWN_DEBT and _over_limit(measure)
    ]
    assert not offenders, (
        "Functions exceed the complexity guardrail — extract-method before merging:\n"
        + "\n".join(offenders)
    )


def test_known_debt_only_shrinks():
    """Ledger entries may not grow, go stale, or linger once within limits."""
    measures = measure_repo()
    problems = []
    for key, recorded in KNOWN_DEBT.items():
        measure = measures.get(key)
        if measure is None:
            problems.append(f"  {key}: no longer exists — remove its KNOWN_DEBT entry")
        elif (measure["cyclomatic"] > recorded["cyclomatic"]
              or measure["cognitive"] > recorded["cognitive"]):
            problems.append(
                f"  {key}: grew beyond its recorded debt "
                f"(cyclomatic {measure['cyclomatic']} vs {recorded['cyclomatic']}, "
                f"cognitive {measure['cognitive']} vs {recorded['cognitive']})")
        elif not _over_limit(measure):
            problems.append(f"  {key}: now within limits — remove its KNOWN_DEBT entry")
        elif (measure["cyclomatic"] < recorded["cyclomatic"]
              or measure["cognitive"] < recorded["cognitive"]):
            problems.append(
                f"  {key}: improved — ratchet the entry down to "
                f"cyclomatic={measure['cyclomatic']}, cognitive={measure['cognitive']}")
    assert not problems, "KNOWN_DEBT ledger out of date:\n" + "\n".join(problems)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failures else 0)
