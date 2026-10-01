"""CLI plumbing: one run coordinate as a branch, and the guard that keeps branches aligned.

Shared by every entrypoint that takes coordinate axes (``main``, ``plot.build``). Argparse
concern only — nothing here knows what a coordinate means, which is why it sits in ``utils``
and not beside ``RunContext``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable


def axis(name: str, choices: tuple[str, ...] | None = None) -> Callable[[str], tuple[str, ...]]:
    """An argparse type for one run coordinate as a branch: ``a`` or ``a:b:c``."""
    def parse(spec: str) -> tuple[str, ...]:
        values = tuple(spec.split(":"))
        if choices is not None:
            bad = [v for v in values if v not in choices]
            if bad:
                raise argparse.ArgumentTypeError(
                    f"Unknown {name} {bad}; choose from {', '.join(sorted(choices))}.")
        return values
    return parse


def assert_uniform(parser: argparse.ArgumentParser, axes: dict[str, tuple[str, ...]]) -> None:
    """Reject ragged branches — one branch length is allowed beside the pinned length 1.

    A coordinate is either held across every run or carries one value per run.
    ``--reduction a:b`` against ``--period x:y:z`` is a mistake, not a request for the
    six-run cross product.
    """
    n = max(len(values) for values in axes.values())
    ragged = {k: v for k, v in axes.items() if len(v) not in (1, n)}
    if ragged:
        parser.error(
            f"Coordinate axes must be length 1 or {n}; got "
            + ", ".join(f"--{k} with {len(v)}" for k, v in ragged.items())
            + ". Pin a coordinate to one value, or give it one value per run.")
