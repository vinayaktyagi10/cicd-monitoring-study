#!/usr/bin/env python3
"""Writes the paper's guest THP sweep table from vm_thp_matrix.csv (zero-filled allocation only).

    python3 thp_vm_table.py <vm_thp_matrix.csv> <out.tex>
"""
import csv
import sys

POLICY_ORDER = {"always": 0, "madvise": 1, "never": 2}
THRESHOLDS = (409, 511)


def summarize(rows):
    out = {}
    for r in rows:
        if int(r["stride"]) != 0 or int(r["max_ptes_none"]) not in THRESHOLDS:
            continue
        cell = out.setdefault((r["thp_enabled"], int(r["shrink_underused"])), {})
        k, n = cell.get(int(r["max_ptes_none"]), (0, 0))
        cell[int(r["max_ptes_none"])] = (k + (r["oom_killed"] == "True"), n + 1)
    return dict(sorted(out.items(), key=lambda kv: (POLICY_ORDER[kv[0][0]], kv[0][1])))


def build_table(rows):
    cells = summarize(rows)
    thresholds = sorted(THRESHOLDS)
    lines = ["\\begin{tabular}{llrr}", "\\toprule",
             "THP policy & \\texttt{shrink\\_underused} & " + " & ".join(f"\\texttt{{max\\_ptes\\_none}}\\,={m}"
                                                                          for m in thresholds) + " \\\\",
             "\\midrule"]
    for (thp, shrink), v in cells.items():
        lines.append(f"{thp} & {shrink} & " + " & ".join(
            f"{v[m][0]}/{v[m][1]}" if m in v else "---" for m in thresholds) + " \\\\")
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
