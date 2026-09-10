#!/usr/bin/env python3
"""Experiment 3 — CPU stress detection time via Prometheus.

Brings up app+cadvisor+prometheus (profile "prometheus"), establishes a
baseline process CPU%, then floods /cpu concurrently and polls Prometheus
(at ~scrape_interval resolution) for the first sample where the app's
self-reported process CPU% crosses a fixed threshold. detection_seconds is
measured relative to the moment the stress load started.

Uses the app's own native `app_process_cpu_percent` gauge (sampled in-process
every second from time.process_time() deltas) rather than cAdvisor's
per-container CPU metric — this Docker's containerd-snapshotter storage
driver means cAdvisor can't resolve container name labels here (see
DECISIONS.md, 2026-09-09), so cAdvisor's container-level series are unusable
for a name-filtered query in this environment. A /health-latency proxy was
tried first and rejected: CPython's GIL round-robins fairly at ~5ms
intervals, so tight CPU loops barely move health-endpoint latency even under
heavy load — process CPU% is the honest, directly-detectable signal.
"""
import argparse
import csv
import os
import statistics
import subprocess
import threading
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEALTH_URL = "http://localhost:8000/health"
CPU_URL = "http://localhost:8000/cpu?iterations=8000000"
PROM_QUERY = "http://localhost:9090/api/v1/query"
THRESHOLD_CPU_PERCENT = 60.0  # detect once app_process_cpu_percent exceeds this


def teardown():
    subprocess.run(["docker", "compose", "--profile", "full", "down"], cwd=ROOT, capture_output=True, timeout=60)
    time.sleep(1)


def bring_up():
    subprocess.run(["docker", "compose", "--profile", "prometheus", "up", "-d"], cwd=ROOT, capture_output=True)
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


def query_process_cpu_percent():
    q = "app_process_cpu_percent"
    url = f"{PROM_QUERY}?{urllib.parse.urlencode({'query': q})}"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            import json
            data = json.load(r)
            result = data["data"]["result"]
            if result:
                val = result[0]["value"][1]
                if val != "NaN":
                    return float(val)
    except Exception:
        pass
    return None


def stress_worker(stop_event):
    while not stop_event.is_set():
        try:
            urllib.request.urlopen(CPU_URL, timeout=15).read()
        except Exception:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--stress-workers", type=int, default=8)
    p.add_argument("--max-wait", type=float, default=30.0)
    p.add_argument("--poll-interval", type=float, default=0.5)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp3_cpu_stress.csv")
    args = p.parse_args()

    teardown()
    if not bring_up():
        print("failed to bring up stack")
        return

    time.sleep(6)  # let a few scrapes accumulate before first run

    rows = []
    for i in range(args.runs):
        for _ in range(3):
            query_process_cpu_percent()
            time.sleep(0.3)

        stop_event = threading.Event()
        threads = [threading.Thread(target=stress_worker, args=(stop_event,)) for _ in range(args.stress_workers)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()

        detected_at = None
        peak_cpu = 0.0
        deadline = t0 + args.max_wait
        while time.perf_counter() < deadline:
            cpu_pct = query_process_cpu_percent()
            if cpu_pct is not None:
                peak_cpu = max(peak_cpu, cpu_pct)
                if detected_at is None and cpu_pct >= THRESHOLD_CPU_PERCENT:
                    detected_at = time.perf_counter() - t0
                    break
            time.sleep(args.poll_interval)

        stop_event.set()
        for t in threads:
            t.join(timeout=5)

        rows.append({"run": i + 1, "detection_seconds": detected_at, "peak_cpu_percent": peak_cpu,
                     "detected": detected_at is not None})
        print(f"run {i+1}/{args.runs} detection_seconds={detected_at} peak_cpu_percent={peak_cpu:.1f}")
        time.sleep(3)  # let CPU% settle back to baseline before next run

    teardown()

    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "detection_seconds", "peak_cpu_percent", "detected"])
        if write_header:
            w.writeheader()
        w.writerows(rows)

    detected = [r["detection_seconds"] for r in rows if r["detected"]]
    if detected:
        print(f"mean={statistics.mean(detected):.2f}s stdev={statistics.pstdev(detected):.2f}s "
              f"min={min(detected):.2f}s max={max(detected):.2f}s n={len(detected)}/{args.runs}")


if __name__ == "__main__":
    main()
