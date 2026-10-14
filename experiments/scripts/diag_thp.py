#!/usr/bin/env python3
"""Experiment 4 diagnostic -- why does a zero-filled allocation survive a 150 MB limit?

Runs a standalone probe in a container with the Experiment 4 memory limit (150 MB, no swap),
allocating up to 20 blocks of 20 MB and holding them, in four variants:
zero-filled or one non-zero byte per 4 KiB page, each with the default THP policy or with
THP disabled for the probe process (prctl PR_SET_THP_DISABLE). Per run it records whether the
container was OOM-killed, how many blocks were allocated, and the host's THP counters before
and after (thp_underused_split_page counts huge pages the kernel split because they were mostly
zero). Host-wide counters are read from /proc/vmstat, so run on a quiet host.

    python diag_thp.py [--reps 5] [--out experiments/raw/diag_thp.csv]
"""
import argparse
import csv
import json
import os
import platform
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIMIT_MB, BLOCK_MB, BLOCKS = 150, 20, 20
COUNTERS = ("thp_underused_split_page", "thp_split_page", "thp_fault_alloc", "thp_deferred_split_page")

PROBE = '''
import ctypes, sys
mode, thp_off = sys.argv[1], sys.argv[2] == "1"
if thp_off:
    ctypes.CDLL(None).prctl(41, 1, 0, 0, 0)
held = []
for n in range(1, %d + 1):
    blk = bytearray(%d * 1024 * 1024)
    if mode == "fill":
        blk[::4096] = b"\\x01" * len(blk[::4096])
    held.append(blk)
    print(n, flush=True)
events = dict(l.split() for l in open("/sys/fs/cgroup/memory.events"))
print("EVENTS", events["max"], events["oom_kill"], flush=True)
''' % (BLOCKS, BLOCK_MB)


def read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def vmstat():
    out = {}
    with open("/proc/vmstat") as fh:
        for line in fh:
            k, v = line.split()
            if k in COUNTERS:
                out[k] = int(v)
    return out


def thp_setting():
    raw = read("/sys/kernel/mm/transparent_hugepage/enabled")
    return next((w.strip("[]") for w in raw.split() if w.startswith("[")), raw)


def run_once(probe_path, mode, thp_off):
    name = "thpdiag"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    before = vmstat()
    subprocess.run(["docker", "run", "--name", name, "--memory", f"{LIMIT_MB}m", "--memory-swap", f"{LIMIT_MB}m",
                    "-v", f"{probe_path}:/p.py:ro", "python:3.12-slim", "python", "/p.py", mode,
                    "1" if thp_off else "0"], capture_output=True, text=True)
    after = vmstat()
    state = json.loads(subprocess.run(["docker", "inspect", "--format", "{{json .State}}", name],
                                      capture_output=True, text=True).stdout)
    logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout.split()
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    blocks = max([int(x) for x in logs if x.isdigit()] or [0])
    ev = logs[logs.index("EVENTS") + 1:logs.index("EVENTS") + 3] if "EVENTS" in logs else ["", ""]
    return {"oom_killed": state["OOMKilled"], "exit_code": state["ExitCode"], "blocks_reached": blocks,
            "cgroup_max_events": ev[0], "cgroup_oom_kill_events": ev[1],
            **{f"d_{k}": after[k] - before[k] for k in COUNTERS}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--out", default=os.path.join(ROOT, "experiments", "raw", "diag_thp.csv"))
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        probe = os.path.join(tmp, "p.py")
        with open(probe, "w") as fh:
            fh.write(PROBE)
        rows = []
        for rep in range(1, args.reps + 1):
            for mode, thp_off in (("zero", False), ("zero", True), ("fill", False), ("fill", True)):
                r = run_once(probe, mode, thp_off)
                rows.append({"rep": rep, "fill": mode == "fill", "thp_disabled_for_probe": thp_off,
                             "limit_mb": LIMIT_MB, "block_mb": BLOCK_MB, "max_blocks": BLOCKS,
                             "host_thp_enabled": thp_setting(),
                             "host_shrink_underused": read("/sys/kernel/mm/transparent_hugepage/shrink_underused"),
                             "kernel": platform.release(), **r})
                print({k: rows[-1][k] for k in ("rep", "fill", "thp_disabled_for_probe", "oom_killed",
                                                "blocks_reached", "d_thp_underused_split_page")})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
