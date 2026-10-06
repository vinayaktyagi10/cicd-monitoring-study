#!/usr/bin/env python3
"""Regenerates Fig. 3 (Grafana dashboard screenshot).

Brings up the full stack, drives a fixed scripted workload (steady /health
and /cpu traffic, one CPU burst, one /memory allocation) so every panel has
data, then captures the provisioned dashboard with headless Chromium at the
original figure's viewport (1532x784, last 15 minutes, 5s refresh).

A live dashboard cannot reproduce pixel-for-pixel (the time axis alone
differs per capture); what is fixed here is the stack, the dashboard JSON,
the workload, the viewport and the time range. Runs as its own Compose
project ("fig3capture") so it starts from empty Prometheus/Grafana volumes
and never touches the main stack's data. Stop the main stack first (same ports).

    python paper/figures/capture_grafana.py [--out paper/figures/fig3_grafana_dashboard.jpg]
"""
import argparse
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DASHBOARD = "http://localhost:3000/d/cicd-monitoring-study-app/?orgId=1&from=now-15m&to=now&refresh=5s"
WIDTH, HEIGHT = 1532, 784
COMPOSE = ["docker", "compose", "-p", "fig3capture", "--profile", "full"]


def get(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
            return r.status
    except Exception:
        return 0


def wait(url, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if get(url, 2) == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f"{url} not ready")


def workload(seconds):
    stop = time.time() + seconds

    def loop(url, period):
        while time.time() < stop:
            get(url)
            time.sleep(period)

    threads = [threading.Thread(target=loop, args=("http://localhost:8000/health", 0.33)),
               threading.Thread(target=loop, args=("http://localhost:8000/cpu", 0.6))]
    for t in threads:
        t.start()
    time.sleep(seconds / 3)
    burst = [threading.Thread(target=get, args=("http://localhost:8000/cpu?iterations=8000000", 30))
             for _ in range(4)]
    for t in burst:
        t.start()
    get("http://localhost:8000/memory?mb=15&hold=true")
    for t in threads + burst:
        t.join()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(HERE, "fig3_grafana_dashboard.jpg"))
    p.add_argument("--traffic-seconds", type=int, default=90)
    p.add_argument("--keep-up", action="store_true")
    args = p.parse_args()

    browser = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chromium-browser")
    if not browser:
        raise SystemExit("needs chromium or google-chrome on PATH")

    subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, capture_output=True)
    subprocess.run([*COMPOSE, "up", "-d"], cwd=ROOT, check=True)
    try:
        wait("http://localhost:8000/health")
        wait("http://localhost:9090/-/ready")
        wait("http://localhost:3000/api/health")
        workload(args.traffic_seconds)
        time.sleep(10)
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "shot.png")
            subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            f"--user-data-dir={tmp}/profile", f"--window-size={WIDTH},{HEIGHT}",
                            "--virtual-time-budget=15000", f"--screenshot={png}", DASHBOARD],
                           check=True, capture_output=True, timeout=120)
            Image.open(png).convert("RGB").save(args.out, quality=90)
        print(f"wrote {args.out}")
    finally:
        if not args.keep_up:
            subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, capture_output=True)


if __name__ == "__main__":
    main()
