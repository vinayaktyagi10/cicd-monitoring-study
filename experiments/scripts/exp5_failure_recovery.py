#!/usr/bin/env python3
"""Experiments 5 & 6 — application failure detection and recovery time.

Brings up app+cadvisor+prometheus once, then per run: `docker kill` the app
container, poll Prometheus `up{job="app"}` until it reports 0 (detection
time), `docker start` it back, and poll both /health and `up{job="app"}==1`
until both recover (recovery time).
"""
import argparse
import csv
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEALTH_URL = "http://localhost:8000/health"
PROM_QUERY = "http://localhost:9090/api/v1/query"
CONTAINER = "cicd-monitoring-study-app-1"


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


def query_up():
    q = 'up{job="app"}'
    url = f"{PROM_QUERY}?{urllib.parse.urlencode({'query': q})}"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            data = json.load(r)
            result = data["data"]["result"]
            if result:
                return float(result[0]["value"][1])
    except Exception:
        pass
    return None


def health_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--poll-interval", type=float, default=0.3)
    p.add_argument("--max-wait", type=float, default=30.0)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp5_failure_recovery.csv")
    args = p.parse_args()

    teardown()
    if not bring_up():
        print("failed to bring up stack")
        return
    time.sleep(6)

    rows = []
    for i in range(args.runs):
        for _ in range(3):
            query_up()
            time.sleep(0.3)

        t0 = time.perf_counter()
        subprocess.run(["docker", "kill", CONTAINER], capture_output=True)

        detection_seconds = None
        deadline = t0 + args.max_wait
        while time.perf_counter() < deadline:
            up = query_up()
            if up == 0.0:
                detection_seconds = time.perf_counter() - t0
                break
            time.sleep(args.poll_interval)

        t1 = time.perf_counter()
        subprocess.run(["docker", "start", CONTAINER], capture_output=True)

        recovery_seconds = None
        deadline = t1 + args.max_wait
        while time.perf_counter() < deadline:
            if health_ok() and query_up() == 1.0:
                recovery_seconds = time.perf_counter() - t1
                break
            time.sleep(args.poll_interval)

        rows.append({
            "run": i + 1,
            "detection_seconds": detection_seconds,
            "recovery_seconds": recovery_seconds,
        })
        print(f"run {i+1}/{args.runs} detection_seconds={detection_seconds} recovery_seconds={recovery_seconds}")
        time.sleep(2)

    teardown()

    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "detection_seconds", "recovery_seconds"])
        if write_header:
            w.writeheader()
        w.writerows(rows)
    print(f"appended {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
