#!/usr/bin/env python3
"""Experiment 6 -- monitoring overhead vs. total host CPU vs. throughput.

Follow-up to Experiment 2, whose 300-request load lasted ~0.1s while each
`docker stats` CPU reading covers a much longer interval, so app CPU% there
mostly measured whether a sample happened to overlap the burst. Here:

* load runs for a fixed duration (default 20s), closed loop, `concurrency`
  workers, same urllib request as Experiment 2;
* CPU is read from kernel counters at exactly the start and end of that
  window: /proc/stat (whole host), each container's cgroup v2 cpu.stat,
  this process's own CPU (the load generator), and docker-proxy processes;
  "other" = host busy cores minus everything attributed (background noise);
* each run gets a freshly started stack, and case order is shuffled within
  every block (seeded), so case is not confounded with time;
* --pin adds a CPU-isolated arm: app, load generator and monitoring
  containers on disjoint physical cores. If the throughput drop caused by
  monitoring is CPU contention, it should shrink in the pinned arm.

Each run also measures an idle window (no load) for the monitoring stack's
standing cost. One row per run, appended and flushed immediately.
"""
import argparse
import csv
import datetime
import os
import random
import statistics
import subprocess
import threading
import time
import urllib.request

import multiprocessing

import hostmetrics as hm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEALTH_URL = "http://localhost:8000/health"
READY = {"prometheus": "http://localhost:9090/-/ready", "grafana": "http://localhost:3000/api/health",
         "cadvisor": "http://localhost:8080/healthz"}
CASES = {
    "docker": ["app"],
    "docker_cadvisor": ["app", "cadvisor"],
    "docker_prometheus": ["app", "cadvisor", "prometheus"],
    "docker_full": ["app", "cadvisor", "prometheus", "grafana"],
}
CONTAINERS = ["app", "cadvisor", "prometheus", "grafana"]
MONITORING = ["cadvisor", "prometheus", "grafana"]


def cname(service):
    return f"cicd-monitoring-study-{service}-1"


def teardown():
    subprocess.run(["docker", "compose", "--profile", "full", "down"], cwd=ROOT, capture_output=True, timeout=120)


def wait_ok(url, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def bring_up(services):
    r = subprocess.run(["docker", "compose", "up", "-d", *services], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"compose up failed: {r.stderr.strip()[-400:]}")
    for s in services:
        url = HEALTH_URL if s == "app" else READY[s]
        if not wait_ok(url):
            raise RuntimeError(f"{s} not ready")


def physical_cores():
    seen, cores = set(), []
    for cpu in sorted(os.sched_getaffinity(0)):
        sib = open(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read().strip()
        if sib not in seen:
            seen.add(sib)
            cores.append(sorted(int(c) for part in sib.split(",") for c in _expand(part)))
    return cores


def _expand(part):
    if "-" in part:
        a, b = part.split("-")
        return range(int(a), int(b) + 1)
    return [int(part)]


def pin_plan():
    cores = physical_cores()
    if len(cores) < 4:
        raise RuntimeError("pinning needs at least 4 physical cores")
    return {"app": cores[1], "loadgen": cores[2], "monitoring": [c for core in cores[3:] for c in core]}


def apply_pin(services, plan):
    for s in services:
        cpus = plan["app"] if s == "app" else plan["monitoring"]
        subprocess.run(["docker", "update", "--cpuset-cpus", ",".join(map(str, cpus)), cname(s)],
                       capture_output=True, check=True)


def proxy_pids():
    out = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open(f"/proc/{pid}/comm") as fh:
                    if fh.read().strip() == "docker-proxy":
                        out.append(pid)
            except OSError:
                pass
    return out


def proc_ticks(pids):
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                f = fh.read().rsplit(")", 1)[1].split()
                total += int(f[11]) + int(f[12])
        except OSError:
            pass
    return total


class Counters:
    def __init__(self, cgroups, pids):
        self.cgroups, self.pids = cgroups, pids

    def read(self):
        return {"t": time.perf_counter(), "host": hm.read_proc_stat(),
                "proxy": proc_ticks(self.pids),
                "cg": {s: hm.read_cgroup_usage(p) for s, p in self.cgroups.items()}}

    def delta(self, a, b, prefix, loadgen_cpu_s=None):
        wall = b["t"] - a["t"]
        hz = os.sysconf("SC_CLK_TCK")
        out = {f"{prefix}_wall_s": wall, f"{prefix}_host_busy_cores": hm.busy_cores(a["host"], b["host"]),
               f"{prefix}_proxy_cores": (b["proxy"] - a["proxy"]) / hz / wall}
        attributed = out[f"{prefix}_proxy_cores"]
        for s in CONTAINERS:
            if s in self.cgroups:
                v = hm.cgroup_cores(a["cg"][s], b["cg"][s], wall)
                out[f"{prefix}_{s}_cores"] = v
                attributed += v
        out[f"{prefix}_monitoring_cores"] = sum(out.get(f"{prefix}_{s}_cores", 0.0) for s in MONITORING)
        if loadgen_cpu_s is not None:
            out["load_loadgen_cores"] = loadgen_cpu_s / wall
            attributed += out["load_loadgen_cores"]
        out[f"{prefix}_other_cores"] = out[f"{prefix}_host_busy_cores"] - attributed
        return out


def one_request():
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as resp:
            resp.read()
            status = resp.status
    except Exception:
        status = 0
    return status, time.perf_counter() - start


def run_load(duration, concurrency):
    deadline = time.perf_counter() + duration
    results = [[] for _ in range(concurrency)]

    def worker(out):
        while time.perf_counter() < deadline:
            out.append(one_request())

    threads = [threading.Thread(target=worker, args=(results[i],)) for i in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    flat = [r for lst in results for r in lst]
    ok = sorted(lat for st, lat in flat if 200 <= st < 300)
    return ok, len(flat) - len(ok)


def _child_load(args):
    duration, concurrency, cpus = args
    if cpus:
        os.sched_setaffinity(0, cpus)
    t = time.process_time()
    ok, errors = run_load(duration, concurrency)
    return ok, errors, time.process_time() - t


def run_load_procs(duration, concurrency, procs, cpus):
    if procs == 1:
        t = time.process_time()
        ok, errors = run_load(duration, concurrency)
        return ok, errors, time.process_time() - t
    split = [concurrency // procs + (i < concurrency % procs) for i in range(procs)]
    with multiprocessing.get_context("fork").Pool(procs) as pool:
        parts = pool.map(_child_load, [(duration, c, cpus) for c in split])
    return sorted(x for p in parts for x in p[0]), sum(p[1] for p in parts), sum(p[2] for p in parts)


def pct(sorted_vals, q):
    if not sorted_vals:
        return ""
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * q))] * 1000


def one_run(case, pinned, args, plan):
    services = CASES[case]
    teardown()
    bring_up(services)
    if pinned:
        apply_pin(services, plan)
    time.sleep(args.settle)

    cgroups = {s: hm.container_cgroup(cname(s)) for s in services}
    counters = Counters(cgroups, proxy_pids())
    row = {"case": case, "pinned": pinned, "loadavg1_before": os.getloadavg()[0]}

    a = counters.read()
    time.sleep(args.idle)
    b = counters.read()
    row.update(counters.delta(a, b, "idle"))

    cpus = plan["loadgen"] if pinned else None
    if cpus:
        os.sched_setaffinity(0, cpus)
    try:
        a = counters.read()
        ok, errors, loadgen_cpu = run_load_procs(args.duration, args.concurrency, args.loadgen_procs, cpus)
        b = counters.read()
    finally:
        os.sched_setaffinity(0, range(os.cpu_count()))
    row.update(counters.delta(a, b, "load", loadgen_cpu))
    wall = row["load_wall_s"]
    row.update({
        "requests_ok": len(ok), "errors": errors, "throughput_ok_rps": len(ok) / wall,
        "mean_latency_ms": statistics.mean(ok) * 1000 if ok else "",
        "p50_latency_ms": pct(ok, 0.50), "p95_latency_ms": pct(ok, 0.95), "p99_latency_ms": pct(ok, 0.99),
    })
    for s in services:
        row[f"{s}_mem_mb"] = hm.read_cgroup_mem_mb(cgroups[s])
    return row


FIELDS = ["timestamp", "block", "order_in_block", "case", "pinned", "seed", "duration_s", "concurrency",
          "loadgen_procs", "settle_s", "loadavg1_before",
          "requests_ok", "errors", "throughput_ok_rps", "mean_latency_ms", "p50_latency_ms",
          "p95_latency_ms", "p99_latency_ms",
          "load_wall_s", "load_host_busy_cores", "load_app_cores", "load_cadvisor_cores",
          "load_prometheus_cores", "load_grafana_cores", "load_monitoring_cores", "load_loadgen_cores",
          "load_proxy_cores", "load_other_cores",
          "idle_wall_s", "idle_host_busy_cores", "idle_app_cores", "idle_cadvisor_cores",
          "idle_prometheus_cores", "idle_grafana_cores", "idle_monitoring_cores", "idle_proxy_cores",
          "idle_other_cores",
          "app_mem_mb", "cadvisor_mem_mb", "prometheus_mem_mb", "grafana_mem_mb", "status"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", nargs="+", default=list(CASES))
    p.add_argument("--pin-cases", nargs="*", default=["docker", "docker_full"],
                   help="cases also run in the CPU-pinned arm (empty to skip the arm)")
    p.add_argument("--runs", type=int, default=20, help="blocks; each block runs every cell once")
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--idle", type=float, default=5.0)
    p.add_argument("--settle", type=float, default=10.0)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--loadgen-procs", type=int, default=1,
                   help="load-generator processes sharing --concurrency (1 = same client as Experiment 2)")
    p.add_argument("--seed", type=int, default=20261006)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp6_overhead.csv")
    args = p.parse_args()

    cells = [(c, False) for c in args.cases] + [(c, True) for c in args.pin_cases]
    plan = pin_plan() if args.pin_cases else None
    if plan:
        print(f"pin plan: app={plan['app']} loadgen={plan['loadgen']} monitoring={plan['monitoring']}")

    if os.path.exists(args.out):
        with open(args.out, newline="") as fh:
            if next(csv.reader(fh)) != FIELDS:
                raise SystemExit(f"{args.out} has a different header; use a new --out")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=FIELDS).writeheader()

    total = len(cells) * args.runs
    done = 0
    for block in range(1, args.runs + 1):
        order = cells[:]
        random.Random(args.seed + block).shuffle(order)
        for k, (case, pinned) in enumerate(order, 1):
            base = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "block": block,
                    "order_in_block": k, "seed": args.seed, "duration_s": args.duration,
                    "concurrency": args.concurrency, "loadgen_procs": args.loadgen_procs,
                    "settle_s": args.settle}
            try:
                row = {**base, **one_run(case, pinned, args, plan), "status": "ok"}
            except Exception as e:
                row = {**base, "case": case, "pinned": pinned, "status": f"error: {e}"}
            with open(args.out, "a", newline="") as fh:
                csv.DictWriter(fh, fieldnames=FIELDS, restval="", extrasaction="raise").writerow(
                    {k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()})
            done += 1
            print(f"[{done}/{total}] block {block} {case:18s} pinned={pinned!s:5s} "
                  f"{row.get('throughput_ok_rps', 0):8.1f} rps  host={row.get('load_host_busy_cores', 0):.2f} "
                  f"app={row.get('load_app_cores', 0):.2f} mon={row.get('load_monitoring_cores', 0):.2f} "
                  f"loadgen={row.get('load_loadgen_cores', 0):.2f} other={row.get('load_other_cores', 0):.2f} "
                  f"{row['status']}", flush=True)
    teardown()


if __name__ == "__main__":
    main()
