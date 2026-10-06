#!/usr/bin/env python3
"""Writes the paper's original-vs-replication table from validate.py's output.

    python3 replication_table.py <original_vs_replication.csv> <out.tex>
"""
import csv
import sys

COLUMNS = ("Metric", "Original mean [95\\% CI]", "Replication mean [95\\% CI]", "$\\Delta$\\%", "Verdict")


def _cell(mean, lo, hi):
    return f"{float(mean):.2f} [{float(lo):.2f}, {float(hi):.2f}]"


def format_row(row):
    name = row["metric"].replace("%", "\\%").replace("&", "\\&")
    verdict = row["verdict"].lower()
    if not row["rep_mean"] or not row["orig_mean"]:
        return f"{name} & --- & --- & --- & {verdict} \\\\"
    delta = float(row["rel_change_pct"])
    return (f"{name} & {_cell(row['orig_mean'], row['orig_ci_lo'], row['orig_ci_hi'])} & "
            f"{_cell(row['rep_mean'], row['rep_ci_lo'], row['rep_ci_hi'])} & "
            f"${delta:+.1f}$ & {verdict} \\\\")


def build_table(rows):
    lines = ["\\begin{tabular}{lllrl}", "\\toprule", " & ".join(COLUMNS) + " \\\\", "\\midrule"]
    lines += [format_row(r) for r in rows]
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(dst, "w") as f:
        f.write(build_table(rows))
    print(f"wrote {dst} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
