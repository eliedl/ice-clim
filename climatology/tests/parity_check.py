"""Parity check between two climatology PNG outputs.

Validates that a refactor preserves (or, when methodology changes,
characterizes the divergence from) a reference output. Used in two regimes:

  - **Same-framework refactor** (e.g. introducing compute_climatology as the
    orchestrator entry point): byte-identical PNGs are expected. Any diff is
    a regression.

  - **Methodology change** (e.g. threshold-then-median -> median-then-threshold
    per DEC-027): a diff is expected. The pixel-level statistics characterize
    the divergence rather than gate it.

Compares both at the byte level (MD5) and, if bytes differ, at the pixel
level (count + magnitude of differing pixels).

Usage:
    python -m climatology.tests.parity_check <reference.png> <candidate.png>
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class ParityResult:
    reference: Path
    candidate: Path
    reference_md5: str
    candidate_md5: str
    byte_identical: bool
    shape: tuple[int, ...] | None = None
    n_pixels_total: int | None = None
    n_pixels_diff: int | None = None
    pct_pixels_diff: float | None = None
    max_abs_diff: int | None = None
    mean_abs_diff: float | None = None
    error: str | None = None


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _load_array(path: Path) -> np.ndarray:
    return np.array(Image.open(path))


def compare(reference: Path, candidate: Path) -> ParityResult:
    ref_md5 = _md5(reference)
    cand_md5 = _md5(candidate)
    result = ParityResult(
        reference=reference,
        candidate=candidate,
        reference_md5=ref_md5,
        candidate_md5=cand_md5,
        byte_identical=ref_md5 == cand_md5,
    )
    if result.byte_identical:
        return result

    ref_arr = _load_array(reference)
    cand_arr = _load_array(candidate)
    if ref_arr.shape != cand_arr.shape:
        result.error = f"shape mismatch: {ref_arr.shape} vs {cand_arr.shape}"
        return result

    diff = np.abs(ref_arr.astype(np.int16) - cand_arr.astype(np.int16))
    differing = np.any(diff > 0, axis=-1) if diff.ndim == 3 else diff > 0

    result.shape = ref_arr.shape
    result.n_pixels_total = int(ref_arr.shape[0] * ref_arr.shape[1])
    result.n_pixels_diff = int(differing.sum())
    result.pct_pixels_diff = 100.0 * result.n_pixels_diff / result.n_pixels_total
    result.max_abs_diff = int(diff.max())
    result.mean_abs_diff = float(diff.mean())
    return result


def report(result: ParityResult) -> str:
    lines = [
        "=== Parity Check ===",
        f"Reference:     {result.reference}",
        f"Candidate:     {result.candidate}",
        f"Reference MD5: {result.reference_md5}",
        f"Candidate MD5: {result.candidate_md5}",
        "",
    ]
    if result.byte_identical:
        lines.append("PARITY: byte-identical")
        return "\n".join(lines)

    lines.append("DIFF DETECTED")
    if result.error:
        lines.append(f"  {result.error}")
        return "\n".join(lines)

    lines += [
        f"  Shape:           {result.shape}",
        f"  Total pixels:    {result.n_pixels_total:,}",
        f"  Differing px:    {result.n_pixels_diff:,} ({result.pct_pixels_diff:.2f}%)",
        f"  Max abs diff:    {result.max_abs_diff}  (0-255 per channel)",
        f"  Mean abs diff:   {result.mean_abs_diff:.4f}",
    ]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python -m climatology.tests.parity_check <reference.png> <candidate.png>")
    ref, cand = Path(sys.argv[1]), Path(sys.argv[2])
    if not ref.exists():
        sys.exit(f"ERROR: reference not found: {ref}")
    if not cand.exists():
        sys.exit(f"ERROR: candidate not found: {cand}")
    print(report(compare(ref, cand)))


if __name__ == "__main__":
    main()
