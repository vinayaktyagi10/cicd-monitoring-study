#!/usr/bin/env python3
"""Samples `docker stats` for named containers at a fixed interval until killed.

Writes one CSV row per (container, sample). Used to capture CPU/memory/
network time series during a load or stress experiment.
"""
import argparse
import csv
import json
import subprocess
import time


def parse_mem(mem_usage):
    # e.g. "12.3MiB / 1.9GiB"
    used = mem_usage.split("/")[0].strip()
    return used


def sample(containers):
    out = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers],
        capture_output=True, text=True, timeout=15,
    )
    rows = []
    ts = time.time()
    for line in out.stdout.strip().splitlines():
        if not line:
            continue
        d = json.loads(line)
        rows.append({
            "timestamp": ts,
            "container": d.get("Name"),
            "cpu_percent": d.get("CPUPerc", "").rstrip("%"),
            "mem_usage": parse_mem(d.get("MemUsage", "")),
            "mem_percent": d.get("MemPerc", "").rstrip("%"),
            "net_io": d.get("NetIO", ""),
        })
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--containers", nargs="+", required=True)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    all_rows = []
    end = time.time() + args.duration
    while time.time() < end:
        try:
            all_rows.extend(sample(args.containers))
        except Exception as e:
            print(f"sample failed: {e}")
        time.sleep(args.interval)

    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["timestamp", "container", "cpu_percent", "mem_usage", "mem_percent", "net_io"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {len(all_rows)} samples to {args.out}")


if __name__ == "__main__":
    main()
