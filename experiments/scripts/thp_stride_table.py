#!/usr/bin/env python3
"""Writes the paper's THP stride-probe table from diag_thp_stride.csv.

    python3 thp_stride_table.py <diag_thp_stride.csv> <out.tex>
"""
import csv
import statistics
import sys

MAX_BLOCKS = 20


def summarize(rows):
    out = []
    for stride in sorted({int(r["stride"]) for r in rows}):
        g = [r for r in rows if int(r["stride"]) == stride]
        zero, m = int(g[0]["zero_subpages"]), int(g[0]["max_ptes_none"])
        splits = [int(r["d_thp_underused_split_page"]) for r in g]
        out.append({"stride": stride, "zero": zero, "predicted": zero > m, "n": len(g),
                    "killed": sum(r["oom_killed"] == "True" for r in g),
                    "blocks": int(statistics.median(min(int(r["blocks_reached"]), MAX_BLOCKS) for r in g)),
                    "splits": (min(splits), max(splits))})
    return out


def build_table(rows):
    lines = ["\\begin{tabular}{rrcrrr}", "\\toprule",
             "Stride & Zero pages & Split predicted & OOM-killed & Blocks & THP splits \\\\",
             "\\midrule"]
    for c in summarize(rows):
        lo, hi = c["splits"]
        sp = f"{lo}" if lo == hi else f"{lo}--{hi}"
        stride = "all zero" if c["stride"] == 0 else str(c["stride"])
        lines.append(f"{stride} & {c['zero']} & {'yes' if c['predicted'] else 'no'} & "
                     f"{c['killed']}/{c['n']} & {c['blocks']} & {sp} \\\\")
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
