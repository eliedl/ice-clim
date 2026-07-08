"""Probe 025 — codebase complexity timeseries: LOC and complexity trajectory per commit (DEC-049).

The 2026-06/07 refactor campaign's success criterion was a *trajectory*, not an
invariant: total LOC shrank ~28 % while features grew. A test cannot gate a trajectory
(a feature commit legitimately adds lines), so the per-function complexity gate
(`climatology/tests/test_complexity.py`) enforces the local invariants and this probe
monitors the global trend. Re-run at the end of a refactor campaign or feature batch
and read the curves.

Measurement is single-sourced: per-function cyclomatic (radon) and cognitive
complexities come from the gate's own `measure_tree`, applied to a `git archive`
snapshot of every commit since the campaign origin. LOC is non-blank lines over the
same file set.

Interpretation guide (see README):
  - totals (panel 1) and LOC (panel 3) are the honest signals;
  - mean-per-function (CSV only) is misleading under refactors that delete trivial
    helpers — the denominator shrinks faster than the numerator (Goodhart);
  - the worst-function line (panel 2) is the standing-debt indicator; flat = untouched.

Read-only on the repo (temp-dir snapshots). Output: timestamped .csv + .png under output/.

Run:
    .venv/bin/python -m backend.probes.025_complexity_timeseries.probe [--since 2026-06-17]
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from climatology.tests.test_complexity import EXCLUDE_PARTS, PACKAGES, REPO_ROOT, measure_tree

# Explicit midnight: git approxidate reads a bare date as "that date at the current
# time of day", which would silently drop same-day commits earlier than the run time.
CAMPAIGN_ORIGIN = "2026-06-17 00:00"
OUTPUT_DIR = Path(__file__).parent / "output"


def _commits(since: str) -> list[tuple[str, str, str]]:
    """(sha, date, subject) for every commit since the origin, oldest first."""
    log = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", f"--since={since}", "--reverse",
         "--date=format:%Y-%m-%d %H:%M", "--pretty=%h|%ad|%s"],
        capture_output=True, text=True, check=True).stdout
    return [tuple(line.split("|", 2)) for line in log.strip().splitlines()]


def _snapshot(sha: str, destination: str) -> None:
    """Extract the production packages of a commit into destination."""
    for package in PACKAGES:
        tar = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", sha, package],
                             capture_output=True)
        if tar.returncode != 0:
            continue  # package absent at this commit
        subprocess.run(["tar", "-x", "-C", destination], input=tar.stdout, check=True)


def _loc(root: Path) -> int:
    """Non-blank LOC over the same file set measure_tree scans."""
    total = 0
    for package in PACKAGES:
        if not (root / package).exists():
            continue
        for file in (root / package).rglob("*.py"):
            if EXCLUDE_PARTS & set(file.parts):
                continue
            total += sum(1 for line in file.read_text().splitlines() if line.strip())
    return total


def _measure_commit(sha: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        _snapshot(sha, tmp)
        root = Path(tmp)
        measures = measure_tree(root)
        n = len(measures)
        cc = [m["cyclomatic"] for m in measures.values()]
        cog = [m["cognitive"] for m in measures.values()]
        return {
            "loc": _loc(root), "n_func": n,
            "cc_total": sum(cc), "cc_mean": round(sum(cc) / n, 2) if n else 0,
            "cc_max": max(cc, default=0),
            "cog_total": sum(cog), "cog_mean": round(sum(cog) / n, 2) if n else 0,
            "cog_max": max(cog, default=0),
        }


def _plot(rows: list[dict], png_path: Path) -> None:
    dates = [datetime.strptime(r["date"], "%Y-%m-%d %H:%M") for r in rows]
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    axes[0].plot(dates, [r["cc_total"] for r in rows], "o-", color="tab:blue", ms=3,
                 label="total cyclomatic")
    axes[0].plot(dates, [r["cog_total"] for r in rows], "s-", color="tab:red", ms=3,
                 label="total cognitive")
    axes[0].set_ylabel("total complexity")
    axes[0].legend()

    axes[1].plot(dates, [r["cc_max"] for r in rows], "o-", color="tab:blue", ms=3,
                 label="cyclomatic max")
    axes[1].plot(dates, [r["cog_max"] for r in rows], "s-", color="tab:red", ms=3,
                 label="cognitive max")
    axes[1].set_ylabel("worst function")
    axes[1].legend()

    axes[2].plot(dates, [r["loc"] for r in rows], "o-", color="tab:green", ms=3)
    axes[2].set_ylabel("LOC (non-blank)", color="tab:green")
    twin = axes[2].twinx()
    twin.plot(dates, [r["n_func"] for r in rows], "s-", color="tab:purple", ms=3)
    twin.set_ylabel("# functions", color="tab:purple")

    for ax in axes:
        ax.grid(alpha=0.3)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.suptitle(f"ice-clim complexity trajectory — {' + '.join(PACKAGES)} (tests excluded)")
    fig.tight_layout()
    fig.savefig(png_path, dpi=130)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=CAMPAIGN_ORIGIN,
                        help=f"trajectory origin date (default {CAMPAIGN_ORIGIN}, fixed "
                             "so re-runs extend the same curve)")
    args = parser.parse_args()

    rows = []
    for sha, date, subject in _commits(args.since):
        row = {"sha": sha, "date": date, "subject": subject[:60], **_measure_commit(sha)}
        rows.append(row)
        print(f"{sha} {date} LOC={row['loc']:5d} funcs={row['n_func']:3d} "
              f"CC total={row['cc_total']:3d} max={row['cc_max']:2d} | "
              f"COG total={row['cog_total']:3d} max={row['cog_max']:2d}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"{stamp}.csv"
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    png_path = OUTPUT_DIR / f"{stamp}.png"
    _plot(rows, png_path)

    first, last = rows[0], rows[-1]
    print(f"\n{first['date']} -> {last['date']}  "
          f"LOC {first['loc']} -> {last['loc']} ({100 * (last['loc'] / first['loc'] - 1):+.1f}%)  "
          f"COG total {first['cog_total']} -> {last['cog_total']} "
          f"({100 * (last['cog_total'] / first['cog_total'] - 1):+.1f}%)  "
          f"worst {first['cog_max']} -> {last['cog_max']}")
    print(f"saved: {csv_path}\nsaved: {png_path}")


if __name__ == "__main__":
    main()