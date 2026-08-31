"""Complexity gate — fails when a function exceeds the guardrail."""
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


# Receivers are bound by the call, not supplied by the caller — they are not interface size.
RECEIVER_ARGS = {"self", "cls"}


def _param_names(node: ast.AST) -> set[str]:
    """Caller-supplied parameter names of a function."""
    args = node.args
    return {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs} - RECEIVER_ARGS


def _arity(node: ast.AST) -> int:
    """Interface size: caller-supplied parameters, ``*args``/``**kwargs`` included."""
    return len(_param_names(node)) + bool(node.args.vararg) + bool(node.args.kwarg)


def _bare_name_arguments(node: ast.AST) -> list[ast.Name]:
    """Every bare-name argument handed to a call inside the body, nested scopes included."""
    passed = []
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        passed += [a for a in call.args if isinstance(a, ast.Name)]
        passed += [k.value for k in call.keywords if isinstance(k.value, ast.Name)]
    return passed


def _tramp_params(node: ast.AST) -> int:
    """Count parameters whose every use is forwarding them onward — Fowler's data tramps."""
    names = _param_names(node)
    forwarded = [n for n in _bare_name_arguments(node) if n.id in names]
    # A name reaching the body any other way is genuinely used here, not merely passing through.
    forwarded_ids = {id(n) for n in forwarded}
    used = {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and id(n) not in forwarded_ids}
    return len({n.id for n in forwarded} - used)


def measure_tree(root: Path) -> dict[str, dict]:
    """Measure control-flow complexity and interface coupling for every production function under root, keyed by path::qualname.

    ``arity``/``tramp`` are measured but not gated: they are the interface axis probe 025
    plots, invisible to the cyclomatic/cognitive limits enforced below.
    """
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
                    "arity": _arity(node),
                    "tramp": _tramp_params(node),
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
    """No function may exceed the complexity limits."""
    offenders = [
        _describe(key, measure)
        for key, measure in measure_repo().items()
        if _over_limit(measure)
    ]
    assert not offenders, (
        "Functions exceed the complexity guardrail — extract-method before merging:\n"
        + "\n".join(offenders)
    )


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
