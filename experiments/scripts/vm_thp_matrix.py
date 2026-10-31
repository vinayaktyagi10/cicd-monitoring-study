#!/usr/bin/env python3
"""Host-wide THP sweep for the Experiment 4 explanation, run as root inside a guest.

Writes the guest's /sys/kernel/mm/transparent_hugepage knobs, runs the stride probe of
diag_thp_stride.py in a 150 MB container for each cell, and restores the settings.

    sudo python3 vm_thp_matrix.py [--reps 3] [--out vm_thp_matrix.csv]
"""
import argparse
import csv
import os
import platform
import tempfile

import diag_thp as d
import diag_thp_stride as ds

THP = "/sys/kernel/mm/transparent_hugepage"
KNOBS = {"enabled": f"{THP}/enabled", "shrink_underused": f"{THP}/shrink_underused",
         "max_ptes_none": f"{THP}/khugepaged/max_ptes_none"}

SWEEP_A = [(e, s, m, k) for e in ("always", "madvise", "never") for s in (0, 1) for m in (409, 511)
           for k in (0, 2, 8)]
SWEEP_B = [("always", 1, m, k) for m in (409, 511) for k in (0, 4, 5, 6, 8)]
SWEEP_C = [("always", 1, m, 0) for m in (0, 200, 409, 500, 510, 511)]


def current(name):
    raw = open(KNOBS[name]).read().strip()
    return raw.split("[")[1].split("]")[0] if "[" in raw else raw


def put(name, value):
    with open(KNOBS[name], "w") as fh:
        fh.write(str(value))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--out", default="vm_thp_matrix.csv")
    args = p.parse_args()
    saved = {k: current(k) for k in KNOBS}
    cells = list(dict.fromkeys(SWEEP_A + SWEEP_B + SWEEP_C))
    rows = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            probe = os.path.join(tmp, "p.py")
            with open(probe, "w") as fh:
                fh.write(ds.PROBE)
            os.chmod(tmp, 0o755)
            os.chmod(probe, 0o644)
            for enabled, shrink, mpn, stride in cells:
                put("enabled", enabled)
                put("shrink_underused", shrink)
                put("max_ptes_none", mpn)
                nz = 512 // stride if stride else 0
                for rep in range(1, args.reps + 1):
                    r = ds.run_once(probe, stride)
                    rows.append({"rep": rep, "thp_enabled": enabled, "shrink_underused": shrink,
                                 "max_ptes_none": mpn, "stride": stride, "zero_subpages": 512 - nz,
                                 "predicted_underused": (512 - nz) > mpn, "kernel": platform.release(), **r})
                    print({k: rows[-1][k] for k in ("thp_enabled", "shrink_underused", "max_ptes_none", "stride",
                                                    "oom_killed", "blocks_reached", "d_thp_underused_split_page")},
                          flush=True)
    finally:
        for k, v in saved.items():
            put(k, v)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
