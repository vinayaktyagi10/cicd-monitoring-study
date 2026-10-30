#!/usr/bin/env python3
"""Prediction test for the Experiment 4 explanation (a companion to diag_thp.py).

The kernel documentation calls a huge page underused when its zero-filled pages exceed
khugepaged/max_ptes_none. With max_ptes_none = M, a 2 MiB page (512 subpages) that has
n non-zero subpages is underused when 512 - n > M. Writing one non-zero byte into every
k-th 4 KiB page gives n = 512/k, so the prediction is: OOM kill when 512 - 512/k <= M,
survival when it is larger. Same container as diag_thp.py (150 MB, no swap, 20 x 20 MB
blocks), default THP policy, host-wide counters read from /proc/vmstat.

    python diag_thp_stride.py [--reps 5] [--strides 0 2 4 5 6 8] [--out ...]
"""
import argparse
import csv
import json
import os
import platform
import subprocess
import tempfile

import diag_thp as d

PROBE = '''
import sys
stride = int(sys.argv[1])
held = []
for n in range(1, %d + 1):
    blk = bytearray(%d * 1024 * 1024)
    if stride:
        blk[::4096 * stride] = b"\\x01" * len(blk[::4096 * stride])
    held.append(blk)
    print(n, flush=True)
events = dict(l.split() for l in open("/sys/fs/cgroup/memory.events"))
print("EVENTS", events["max"], events["oom_kill"], flush=True)
''' % (d.BLOCKS, d.BLOCK_MB)


def run_once(probe_path, stride):
    name = "thpstride"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    before = d.vmstat()
    subprocess.run(["docker", "run", "--name", name, "--memory", f"{d.LIMIT_MB}m", "--memory-swap", f"{d.LIMIT_MB}m",
                    "-v", f"{probe_path}:/p.py:ro", "python:3.12-slim", "python", "/p.py", str(stride)],
                   capture_output=True, text=True)
    after = d.vmstat()
    state = json.loads(subprocess.run(["docker", "inspect", "--format", "{{json .State}}", name],
                                      capture_output=True, text=True).stdout)
    logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout.split()
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    cut = logs.index("EVENTS") if "EVENTS" in logs else len(logs)
    blocks = max([int(x) for x in logs[:cut] if x.isdigit()] or [0])
    return {"oom_killed": state["OOMKilled"], "blocks_reached": blocks,
            **{f"d_{k}": after[k] - before[k] for k in d.COUNTERS}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--strides", type=int, nargs="+", default=[0, 2, 4, 5, 6, 8])
    p.add_argument("--out", default=os.path.join(d.ROOT, "experiments", "raw", "diag_thp_stride.csv"))
    args = p.parse_args()
    m = int(d.read("/sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none") or -1)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = os.path.join(tmp, "p.py")
        with open(probe, "w") as fh:
            fh.write(PROBE)
        for rep in range(1, args.reps + 1):
            for stride in args.strides:
                nz = 512 // stride if stride else 0
                r = run_once(probe, stride)
                rows.append({"rep": rep, "stride": stride, "nonzero_subpages": nz, "zero_subpages": 512 - nz,
                             "max_ptes_none": m, "predicted_underused": (512 - nz) > m,
                             "host_thp_enabled": d.thp_setting(),
                             "host_shrink_underused": d.read("/sys/kernel/mm/transparent_hugepage/shrink_underused"),
                             "kernel": platform.release(), **r})
                print({k: rows[-1][k] for k in ("rep", "stride", "zero_subpages", "predicted_underused",
                                                "oom_killed", "blocks_reached", "d_thp_underused_split_page")}, flush=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
