#!/usr/bin/env python3
"""Writes the paper's Experiment 4 THP diagnostic table from diag_thp.csv.

    python3 thp_table.py <diag_thp.csv> <out.tex>
"""
import csv
import statistics
import sys

CELLS = [(False, False), (False, True), (True, False), (True, True)]


def summarize(rows):
    out = []
    for fill, off in CELLS:
        g = [r for r in rows if (r["fill"] == str(fill)) and (r["thp_disabled_for_probe"] == str(off))]
        splits = [int(r["d_thp_underused_split_page"]) for r in g]
        out.append({"label": "Non-zero" if fill else "Zero-filled", "thp": "disabled" if off else "default",
                    "n": len(g), "killed": sum(r["oom_killed"] == "True" for r in g),
                    "blocks": int(statistics.median(int(r["blocks_reached"]) for r in g)),
                    "splits": (min(splits), max(splits))})
    return out


def build_table(rows):
    lines = ["\\begin{tabular}{llrrr}", "\\toprule",
             "Allocation & THP & OOM-killed & Blocks & THP splits \\\\",
             "\\midrule"]
    for c in summarize(rows):
        lo, hi = c["splits"]
        sp = f"{lo}" if lo == hi else f"{lo}--{hi}"
        lines.append(f"{c['label']} & {c['thp']} & {c['killed']}/{c['n']} & {c['blocks']} & {sp} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(dst, "w") as fh:
        fh.write(build_table(rows))
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
