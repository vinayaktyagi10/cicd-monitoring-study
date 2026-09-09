#!/usr/bin/env python3
"""Experiment 2 — resource utilization, response time, throughput and
monitoring overhead across the three baseline cases.

Case 1: docker             -> app only
Case 2: docker_prometheus  -> app + cadvisor + prometheus  (compose profile "prometheus")
Case 3: docker_full        -> app + cadvisor + prometheus + grafana (profile "full")

Each run: bring the case up, fire a fixed load at /health while sampling
`docker stats` for every container in that case every second, tear down.
One summary row per run (mean/peak resource use + response time + throughput),
plus the monitoring-stack containers' own resource draw for the overhead table.
"""
import argparse
import csv
import json
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = "/home/twirly-reflex/Research/cicd-monitoring-study"
HEALTH_URL = "http://localhost:8000/health"

CASES = {
    "docker": {"profile": None, "containers": ["cicd-monitoring-study-app-1"]},
    "docker_prometheus": {"profile": "prometheus",
                           "containers": ["cicd-monitoring-study-app-1", "cicd-monitoring-study-cadvisor-1", "cicd-monitoring-study-prometheus-1"]},
    "docker_full": {"profile": "full",
                     "containers": ["cicd-monitoring-study-app-1", "cicd-monitoring-study-cadvisor-1",
                                    "cicd-monitoring-study-prometheus-1", "cicd-monitoring-study-grafana-1"]},
}


def teardown():
    subprocess.run(["docker", "compose", "--profile", "full", "down"], cwd=ROOT, capture_output=True, timeout=60)
    time.sleep(1)


def bring_up(profile):
    cmd = ["docker", "compose"]
    if profile:
        cmd += ["--profile", profile, "up", "-d"]
    else:
        cmd += ["up", "-d", "app"]
    subprocess.run(cmd, cwd=ROOT, capture_output=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def sample_stats(containers, stop_event, out_list, interval=1.0):
    while not stop_event.is_set():
        try:
            out = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers],
                capture_output=True, text=True, timeout=10,
            )
            for line in out.stdout.strip().splitlines():
                if not line:
                    continue
                d = json.loads(line)
                out_list.append({
                    "container": d.get("Name"),
                    "cpu_percent": float(d.get("CPUPerc", "0%").rstrip("%") or 0),
                    "mem_mb": _parse_mem_mb(d.get("MemUsage", "0MiB / 0MiB")),
                })
        except Exception:
            pass
        time.sleep(interval)


def _parse_mem_mb(mem_usage):
    used = mem_usage.split("/")[0].strip()
    try:
        if used.endswith("GiB"):
            return float(used[:-3]) * 1024
        if used.endswith("MiB"):
            return float(used[:-3])
        if used.endswith("KiB"):
            return float(used[:-3]) / 1024
        if used.endswith("B"):
            return float(used[:-1]) / (1024 * 1024)
    except ValueError:
        return 0.0
    return 0.0


def one_request():
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as resp:
            resp.read()
            status = resp.status
    except Exception:
        status = 0
    return status, time.perf_counter() - start


def run_load(requests, concurrency):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(one_request) for _ in range(requests)]
        for f in as_completed(futures):
            results.append(f.result())
    wall = time.perf_counter() - t0
    latencies = sorted(r[1] for r in results)
    errors = sum(1 for r in results if r[0] < 200 or r[0] >= 300)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    return {
        "throughput_rps": len(results) / wall,
        "mean_latency_ms": statistics.mean(latencies) * 1000,
        "p95_latency_ms": p95 * 1000,
        "error_rate": errors / len(results),
        "wall_seconds": wall,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", nargs="+", default=list(CASES.keys()))
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--requests", type=int, default=300)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp2_resource.csv")
    args = p.parse_args()

    rows = []
    for case in args.cases:
        spec = CASES[case]
        teardown()
        ok = bring_up(spec["profile"])
        if not ok:
            print(f"[{case}] failed to come up, skipping")
            continue
        time.sleep(3)  # let cadvisor/prometheus settle before sampling
        for i in range(args.runs):
            samples = []
            stop_event = threading.Event()
            t = threading.Thread(target=sample_stats, args=(spec["containers"], stop_event, samples))
            t.start()
            load_result = run_load(args.requests, args.concurrency)
            stop_event.set()
            t.join(timeout=5)

            per_container = {}
            for s in samples:
                per_container.setdefault(s["container"], {"cpu": [], "mem": []})
                per_container[s["container"]]["cpu"].append(s["cpu_percent"])
                per_container[s["container"]]["mem"].append(s["mem_mb"])

            row = {"case": case, "run": i + 1, **load_result}
            for cname, vals in per_container.items():
                short = cname.replace("cicd-monitoring-study-", "").replace("-1", "")
                row[f"{short}_cpu_mean"] = statistics.mean(vals["cpu"]) if vals["cpu"] else ""
                row[f"{short}_mem_mb_mean"] = statistics.mean(vals["mem"]) if vals["mem"] else ""
            rows.append(row)
            print(f"[{case}] run {i+1}/{args.runs} throughput={load_result['throughput_rps']:.1f}rps "
                  f"p95={load_result['p95_latency_ms']:.1f}ms errors={load_result['error_rate']:.3f}")
        teardown()

    fieldnames = sorted({k for r in rows for k in r.keys()})
    import os
    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerows(rows)
    print(f"appended {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
