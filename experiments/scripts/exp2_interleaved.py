#!/usr/bin/env python3
"""Experiment 2 with case order randomized within blocks and a fresh stack per run.

Cases: docker, docker_aa (identical configuration, second label, for the A/A noise
floor), docker_prometheus, docker_full. Each block runs all four in a seeded random
order; each run tears down, brings the case up, settles, and fires Experiment 2's
load once while sampling docker stats.
"""
import argparse
import csv
import datetime
import os
import random
import statistics
import threading
import time

import exp2_resource as e2

ROOT = e2.ROOT
CASES = {**e2.CASES, "docker_aa": e2.CASES["docker"]}
FIELDS = ["timestamp", "block", "position", "case", "run", "throughput_rps", "mean_latency_ms",
          "p95_latency_ms", "error_rate", "wall_seconds", "loadavg1", "app_cpu_mean", "app_mem_mb_mean",
          "cadvisor_cpu_mean", "cadvisor_mem_mb_mean", "prometheus_cpu_mean", "prometheus_mem_mb_mean",
          "grafana_cpu_mean", "grafana_mem_mb_mean"]


def one_run(case, block, position, run):
    spec = CASES[case]
    e2.teardown()
    if not e2.bring_up(spec["profile"]):
        return None
    time.sleep(3)
    samples, stop = [], threading.Event()
    t = threading.Thread(target=e2.sample_stats, args=(spec["containers"], stop, samples))
    t.start()
    load = e2.run_load(300, 10)
    stop.set()
    t.join(timeout=5)
    row = {"timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "block": block, "position": position, "case": case, "run": run,
           "loadavg1": os.getloadavg()[0], **load}
    per = {}
    for s in samples:
        per.setdefault(s["container"], {"cpu": [], "mem": []})
        per[s["container"]]["cpu"].append(s["cpu_percent"])
        per[s["container"]]["mem"].append(s["mem_mb"])
    for cname, v in per.items():
        short = cname.replace("cicd-monitoring-study-", "").replace("-1", "")
        row[f"{short}_cpu_mean"] = statistics.mean(v["cpu"])
        row[f"{short}_mem_mb_mean"] = statistics.mean(v["mem"])
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--blocks", type=int, default=20)
    p.add_argument("--seed", type=int, default=20261030)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp2_interleaved.csv")
    args = p.parse_args()
    rng = random.Random(args.seed)
    new = not os.path.exists(args.out)
    done = {c: 0 for c in CASES}
    for b in range(1, args.blocks + 1):
        order = list(CASES)
        rng.shuffle(order)
        for pos, case in enumerate(order, 1):
            done[case] += 1
            row = one_run(case, b, pos, done[case])
            if row is None:
                print(f"[block {b}] {case} failed to come up, skipped")
                continue
            with open(args.out, "a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                    new = False
                w.writerow({k: row.get(k, "") for k in FIELDS})
            print(f"[block {b}/{args.blocks}] pos {pos} {case:18s} {row['throughput_rps']:.0f} req/s "
                  f"err={row['error_rate']:.3f}", flush=True)
    e2.teardown()


if __name__ == "__main__":
    main()
