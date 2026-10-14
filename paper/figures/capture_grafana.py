#!/usr/bin/env python3
"""Regenerates Fig. 3 (Grafana dashboard panels, one screenshot per panel).

Brings up the full stack, drives a fixed scripted workload (steady /health
and /cpu traffic, one CPU burst, one /memory allocation) so every panel has
data, then captures each provisioned dashboard panel separately (Grafana
solo-panel view, last 5 minutes) with headless Chromium at 2x device scale.

A live dashboard cannot reproduce pixel-for-pixel (the time axis alone
differs per capture); what is fixed here is the stack, the dashboard JSON,
the workload, the viewport and the time range. Runs as its own Compose
project ("fig3capture") so it starts from empty Prometheus/Grafana volumes
and never touches the main stack's data. Stop the main stack first (same ports).

    python paper/figures/capture_grafana.py [--outdir paper/figures]
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PANEL_URL = ("http://localhost:3000/d-solo/cicd-monitoring-study-app/?orgId=1&from=now-5m&to=now"
             "&panelId={id}&width={w}&height={h}")
PANELS = [(1, "request_rate", 800, 400), (2, "latency_p95", 800, 400),
          (3, "cpu", 800, 400), (4, "memory", 800, 400), (5, "target_up", 1600, 300)]
SCALE = 2
CHROME_PX = 88
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


def dump_panel_data(path, minutes=5, step=5):
    with open(os.path.join(ROOT, "monitoring", "grafana", "provisioning", "dashboards",
                           "app-dashboard.json")) as fh:
        dash = json.load(fh)
    end = time.time()
    out = {"captured_unix": end, "window_s": minutes * 60, "step_s": step, "panels": {}}
    for panel in dash["panels"]:
        series = []
        for target in panel["targets"]:
            q = urllib.parse.urlencode({"query": target["expr"], "start": end - minutes * 60,
                                        "end": end, "step": step})
            with urllib.request.urlopen(f"http://localhost:9090/api/v1/query_range?{q}", timeout=10) as r:
                series += json.load(r)["data"]["result"]
        out["panels"][str(panel["id"])] = {"title": panel["title"], "series": series}
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"wrote {path}")


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
    p.add_argument("--outdir", default=HERE)
    p.add_argument("--panel-data", default=os.path.join(ROOT, "experiments", "raw", "grafana_panels.json"))
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
        dump_panel_data(args.panel_data)
        with tempfile.TemporaryDirectory() as tmp:
            for pid, name, w, h in PANELS:
                png = os.path.join(tmp, f"{name}.png")
                subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                f"--user-data-dir={tmp}/profile", f"--window-size={w},{h + CHROME_PX}",
                                f"--force-device-scale-factor={SCALE}",
                                "--virtual-time-budget=15000", f"--screenshot={png}",
                                PANEL_URL.format(id=pid, w=w, h=h)],
                               check=True, capture_output=True, timeout=120)
                out = os.path.join(args.outdir, f"fig3_grafana_{name}.png")
                Image.open(png).convert("RGB").crop((0, 0, w * SCALE, h * SCALE)).save(out)
                print(f"wrote {out}")
    finally:
        if not args.keep_up:
            subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, capture_output=True)


if __name__ == "__main__":
    main()
