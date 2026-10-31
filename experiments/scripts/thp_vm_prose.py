#!/usr/bin/env python3
"""Checks every guest-sweep number quoted in paper/paper.tex against vm_thp_matrix.csv.

    python3 thp_vm_prose.py <vm_thp_matrix.csv> <paper.tex>
"""
import csv
import re
import sys


def cell(rows, thp, shrink, mpn, stride):
    return [r for r in rows if (r["thp_enabled"], int(r["shrink_underused"]), int(r["max_ptes_none"]),
                                int(r["stride"])) == (thp, shrink, mpn, stride)]


def killed(g):
    return sum(r["oom_killed"] == "True" for r in g)


def claims(rows):
    reps = {len(cell(rows, "always", 1, 409, s)) for s in (0, 2, 4, 5, 6, 8)}
    assert len(reps) == 1, "unequal runs per stride"
    n = reps.pop()
    swept = [cell(rows, "always", 1, m, 0) for m in (0, 200, 409, 500, 510)]
    assert all(killed(g) == 0 and len(g) == n for g in swept), "zero-fill did not escape for every swept value"
    assert killed(cell(rows, "always", 1, 511, 0)) == n, "zero-fill escaped at 511"
    splits = [int(r["d_thp_underused_split_page"]) for g in swept for r in g]
    stride = {s: cell(rows, "always", 1, 409, s) for s in (2, 4, 5, 6, 8)}
    blocks5 = [int(r["blocks_reached"]) for r in stride[5]]
    assert killed(stride[2]) == killed(stride[4]) == killed(stride[5]) == n
    assert killed(stride[6]) == killed(stride[8]) == 0
    assert all(int(r["blocks_reached"]) == 20 for s in (6, 8) for r in stride[s])
    return [f"{n} runs per cell", f"(0/{n} killed each, {min(splits)}--{max(splits)} splits per run)",
            f"strides 2 and 4 were killed in {n}/{n} runs, stride 5 in {n}/{n} after {min(blocks5)}--{max(blocks5)} blocks",
            f"strides 6 and 8 survived all 20 blocks in {n}/{n}"]


def main():
    with open(sys.argv[1], newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(sys.argv[2]) as fh:
        paper = re.sub(r"\s+", " ", fh.read())
    c = claims(rows)
    misses = [s for s in c if s not in paper]
    for s in c:
        print(("MATCH     " if s in paper else "NOT FOUND ") + s)
    sys.exit(1 if misses else 0)


if __name__ == "__main__":
    main()
