#!/usr/bin/env python3
"""Aggregates raw per-run CSVs into mean/std/min/max summary tables.

Reads every experiments/raw/*.csv, groups by the categorical column
(config/case, or the whole file for single-config experiments), computes
mean/stdev/min/max for each numeric column, writes one summary CSV per
input file into experiments/results/.

Each expN raw CSV has been re-run more than once since the original data
collection (fresh demo samples, the 2026-09-10 reproduction investigation
-- see experiments/reproduction_run_2026-09-10.txt and
experiments/DATA_PROVENANCE.md), and every script appends rather than
overwrites. By default this script only aggregates the ORIGINAL pass for
each file -- the exact row count that results/*_summary.csv and the
paper's tables were built from -- so re-running this never silently
changes the paper's reported numbers by mixing in later runs. Pass --all
to aggregate every row in the file instead (useful for inspecting a fresh
demo sample on its own, never for regenerating the paper's tables).
"""
import argparse
import csv
import glob
import os
import statistics

EXPERIMENTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(EXPERIMENTS_DIR, "raw")
OUT_DIR = os.path.join(EXPERIMENTS_DIR, "results")

GROUP_COLUMNS = ["config", "case"]

# Row count of the original data-collection pass, per raw file -- rows
# beyond this are later re-runs (demo samples, reproduction investigation)
# and must be excluded from the numbers reported in the paper.
ORIGINAL_PASS_ROWS = {
    "exp1_deploy": 68,          # 20 manual + 20 docker + 20 full_pipeline + 8 docker_cicd
    "exp2_resource": 60,        # 20 runs x 3 cases
    "exp3_cpu_stress": 20,
    "exp4_memory_stress": 20,
    "exp5_failure_recovery": 20,
}


def to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def summarize(rows, group_col, out_path):
    groups = {}
    for row in rows:
        key = row.get(group_col, "all") if group_col else "all"
        groups.setdefault(key, []).append(row)

    numeric_cols = []
    for col in rows[0].keys():
        if col == group_col:
            continue
        if any(to_float(r[col]) is not None for r in rows):
            numeric_cols.append(col)

    out_rows = []
    for key, group_rows in groups.items():
        n_total = len(group_rows)
        summary = {"config": key, "n_runs": n_total}
        for col in numeric_cols:
            vals = [to_float(r[col]) for r in group_rows]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            summary[f"{col}_mean"] = round(statistics.mean(vals), 4)
            summary[f"{col}_std"] = round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0
            summary[f"{col}_min"] = round(min(vals), 4)
            summary[f"{col}_max"] = round(max(vals), 4)
            summary[f"{col}_n"] = len(vals)
        out_rows.append(summary)

    fieldnames = sorted({k for r in out_rows for k in r.keys()}, key=lambda k: (k != "config", k != "n_runs", k))
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {out_path} ({len(out_rows)} groups, {len(numeric_cols)} metrics)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true",
                    help="aggregate every row, not just the original pass "
                         "(never use this to regenerate the paper's tables)")
    args = p.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    for path in sorted(glob.glob(f"{RAW_DIR}/*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue

        cap = ORIGINAL_PASS_ROWS.get(name)
        if cap is not None and not args.all and len(rows) > cap:
            print(f"{name}: using original pass only ({cap} of {len(rows)} rows "
                  f"-- pass --all to include later re-runs)")
            rows = rows[:cap]

        group_col = next((c for c in GROUP_COLUMNS if c in rows[0]), None)
        out_path = f"{OUT_DIR}/{name}_summary.csv"
        summarize(rows, group_col, out_path)


if __name__ == "__main__":
    main()
