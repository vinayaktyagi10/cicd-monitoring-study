#!/usr/bin/env python3
"""Experiment 7 -- does the monitoring cost grow with background CPU load?

Experiment 6 bounded the monitoring stack's throughput cost at about 1.4% on an otherwise
idle host. If that cost were CPU contention it should grow as the host gets busier. This
experiment holds the host at a target CPU utilization (default 0, 20, 40 and 60%) with a
duty-cycle burner on every logical CPU, and measures keep-alive throughput with the app alone
(docker) and with the full monitoring stack (docker_full), case and level shuffled inside each
block (seeded), fresh stack per run, CPU read from kernel counters over the load window.

Analysis fixed before any data was collected (see analyze_loaded.py):
  primary   difference in throughput (docker_full - docker) at 0% and at 60%, and their
            difference-in-differences with a percentile bootstrap 95% CI;
  secondary the same contrast at 20% and 40%, each with a Welch 95% CI;
  contention is supported only if the monitoring penalty grows with load (DiD CI excludes 0 in
  the direction of a larger penalty); a CI containing 0 is reported as not supported, not as
  evidence of no effect.
The achieved utilization is measured, not assumed: burner CPU comes from /proc/<pid>/stat.
Unpinned, so the burner competes with the application, load generator and monitoring.

One row per run, appended and flushed immediately.
"""
import argparse
import csv
import datetime
import multiprocessing
import os
import random
import statistics
import time

import exp6_overhead as e6
import hostmetrics as hm

ROOT = e6.ROOT
PERIOD_S = 0.02

FIELDS = ["timestamp", "block", "order_in_block", "case", "bg_target_pct", "seed", "duration_s", "concurrency",
          "loadgen_procs", "keepalive", "settle_s", "loadavg1_before",
          "requests_ok", "errors", "throughput_ok_rps", "mean_latency_ms", "p50_latency_ms",
          "p95_latency_ms", "p99_latency_ms",
          "load_wall_s", "load_host_busy_cores", "load_burner_cores", "load_app_cores", "load_cadvisor_cores",
          "load_prometheus_cores", "load_grafana_cores", "load_monitoring_cores", "load_loadgen_cores",
          "load_proxy_cores", "load_other_cores",
          "idle_wall_s", "idle_host_busy_cores", "idle_burner_cores", "idle_app_cores", "idle_cadvisor_cores",
          "idle_prometheus_cores", "idle_grafana_cores", "idle_monitoring_cores", "idle_proxy_cores",
          "idle_other_cores",
          "app_mem_mb", "cadvisor_mem_mb", "prometheus_mem_mb", "grafana_mem_mb", "status"]


def duty_schedule(target_pct, period=PERIOD_S):
    """(busy_seconds, sleep_seconds) per period for a worker that should use target_pct% of one CPU."""
    f = min(max(target_pct, 0.0), 100.0) / 100.0
    return period * f, period * (1.0 - f)


def _burn(target_pct):
    busy, idle = duty_schedule(target_pct)
    while True:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < busy:
            pass
        if idle > 0:
            time.sleep(idle)


class Burner:
    def __init__(self, target_pct, workers):
        self.target_pct, self.workers, self.procs = target_pct, workers, []

    def start(self):
        if self.target_pct <= 0:
            return
        ctx = multiprocessing.get_context("fork")
        self.procs = [ctx.Process(target=_burn, args=(self.target_pct,), daemon=True) for _ in range(self.workers)]
        for p in self.procs:
            p.start()

    def pids(self):
        return [str(p.pid) for p in self.procs]

    def stop(self):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            p.join(timeout=5)
        self.procs = []


def one_run(case, bg_pct, args):
    services = e6.CASES[case]
    e6.teardown()
    e6.bring_up(services)
    burner = Burner(bg_pct, os.cpu_count())
    burner.start()
    try:
        time.sleep(args.settle)
        cgroups = {s: hm.container_cgroup(e6.cname(s)) for s in services}
        counters = e6.Counters(cgroups, e6.proxy_pids())
        row = {"case": case, "loadavg1_before": os.getloadavg()[0]}
        hz = os.sysconf("SC_CLK_TCK")

        def window(prefix, fn):
            a, ta = counters.read(), e6.proc_ticks(burner.pids())
            result = fn()
            b, tb = counters.read(), e6.proc_ticks(burner.pids())
            d = counters.delta(a, b, prefix, result[2] if result else None)
            burn = (tb - ta) / hz / d[f"{prefix}_wall_s"]
            d[f"{prefix}_burner_cores"] = burn
            d[f"{prefix}_other_cores"] -= burn
            return d, result

        d, _ = window("idle", lambda: (time.sleep(args.idle), None, None))
        row.update(d)
        d, res = window("load", lambda: e6.run_load_procs(args.duration, args.concurrency, args.loadgen_procs,
                                                         None, args.keepalive))
    finally:
        burner.stop()
    ok, errors, _ = res
    row.update(d)
    wall = row["load_wall_s"]
    row.update({"requests_ok": len(ok), "errors": errors, "throughput_ok_rps": len(ok) / wall,
                "mean_latency_ms": statistics.mean(ok) * 1000 if ok else "",
                "p50_latency_ms": e6.pct(ok, 0.50), "p95_latency_ms": e6.pct(ok, 0.95),
                "p99_latency_ms": e6.pct(ok, 0.99)})
    for s in services:
        row[f"{s}_mem_mb"] = hm.read_cgroup_mem_mb(cgroups[s])
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", nargs="+", default=["docker", "docker_full"])
    p.add_argument("--levels", nargs="+", type=float, default=[0, 20, 40, 60])
    p.add_argument("--runs", type=int, default=15, help="blocks; each block runs every cell once")
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--idle", type=float, default=5.0)
    p.add_argument("--settle", type=float, default=10.0)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--loadgen-procs", type=int, default=1)
    p.add_argument("--no-keepalive", dest="keepalive", action="store_false")
    p.add_argument("--seed", type=int, default=20261014)
    p.add_argument("--start-block", type=int, default=1, help="resume an interrupted run at this block")
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp7_loaded_overhead.csv")
    args = p.parse_args()

    cells = [(c, lv) for c in args.cases for lv in args.levels]
    if os.path.exists(args.out):
        with open(args.out, newline="") as fh:
            if next(csv.reader(fh)) != FIELDS:
                raise SystemExit(f"{args.out} has a different header; use a new --out")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=FIELDS).writeheader()

    total, done = len(cells) * (args.runs - args.start_block + 1), 0
    for block in range(args.start_block, args.runs + 1):
        order = cells[:]
        random.Random(args.seed + block).shuffle(order)
        for k, (case, lv) in enumerate(order, 1):
            base = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "block": block,
                    "order_in_block": k, "bg_target_pct": lv, "seed": args.seed, "duration_s": args.duration,
                    "concurrency": args.concurrency, "loadgen_procs": args.loadgen_procs,
                    "keepalive": args.keepalive, "settle_s": args.settle}
            try:
                row = {**base, **one_run(case, lv, args), "status": "ok"}
            except Exception as e:
                row = {**base, "case": case, "status": f"error: {e}"}
            with open(args.out, "a", newline="") as fh:
                csv.DictWriter(fh, fieldnames=FIELDS, restval="", extrasaction="raise").writerow(
                    {k2: (round(v, 6) if isinstance(v, float) else v) for k2, v in row.items()})
            done += 1
            print(f"[{done}/{total}] block {block} {case:12s} bg={lv:4.0f}% "
                  f"{row.get('throughput_ok_rps', 0):8.1f} rps host={row.get('load_host_busy_cores', 0):5.2f} "
                  f"burner={row.get('load_burner_cores', 0):5.2f} mon={row.get('load_monitoring_cores', 0):.3f} "
                  f"{row['status']}", flush=True)
    e6.teardown()


if __name__ == "__main__":
    main()
