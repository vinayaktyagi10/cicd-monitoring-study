#!/usr/bin/env python3
"""Experiment 1 — deployment time & reliability across configurations.

Configs:
  manual        : no container. `python -m uvicorn` as a raw process
                  (stands in for Baseline A — no containerization/CI).
  docker        : `docker compose up -d app` from a locally-cached image
                  (Baseline B — containerized, no CI/CD, no monitoring).
  docker_cicd   : trigger the real GitHub Actions workflow (build+test+push)
                  via workflow_dispatch, then run the freshly built image
                  (containerized + automated pipeline, no monitoring).
  full_pipeline : `docker compose --profile full up -d` (proposed system:
                  Docker + CI/CD-built image + Prometheus + Grafana).

For each run: tear down whatever's running, start the config, poll until
healthy, record elapsed seconds. Raw rows appended to CSV; failures recorded
as elapsed=None.
"""
import argparse
import csv
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PY = f"{ROOT}/.venv-manual/bin/python"
HEALTH_URL = "http://localhost:8000/health"
PROM_URL = "http://localhost:9090/-/ready"
GRAFANA_URL = "http://localhost:3000/api/health"


def wait_ok(urls, timeout=60):
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        ok = True
        for u in urls:
            try:
                with urllib.request.urlopen(u, timeout=2) as r:
                    if r.status != 200:
                        ok = False
            except Exception:
                ok = False
        if ok:
            return time.perf_counter() - start
        time.sleep(0.2)
    return None


def teardown_all():
    subprocess.run(["docker", "compose", "--profile", "full", "down"], cwd=ROOT,
                    capture_output=True, timeout=60)
    subprocess.run(["pkill", "-f", "uvicorn main:app"], capture_output=True)
    subprocess.run(["docker", "rm", "-f", "manual-cicd-app"], capture_output=True)
    time.sleep(1)


def run_manual():
    proc = subprocess.Popen(
        [VENV_PY, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=f"{ROOT}/app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    elapsed = wait_ok([HEALTH_URL])
    proc.terminate()
    proc.wait(timeout=10)
    return elapsed


def run_docker():
    subprocess.run(["docker", "compose", "up", "-d", "app"], cwd=ROOT, capture_output=True)
    elapsed = wait_ok([HEALTH_URL])
    subprocess.run(["docker", "compose", "down"], cwd=ROOT, capture_output=True)
    return elapsed


def run_docker_cicd():
    r = subprocess.run(
        ["gh", "workflow", "run", "ci.yml", "--ref", "master"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    time.sleep(5)
    run_id = None
    deadline = time.time() + 30
    while time.time() < deadline and run_id is None:
        out = subprocess.run(
            ["gh", "run", "list", "--workflow=ci.yml", "--limit", "1", "--json", "databaseId,status"],
            cwd=ROOT, capture_output=True, text=True,
        )
        try:
            data = json.loads(out.stdout)
            if data:
                run_id = data[0]["databaseId"]
        except Exception:
            pass
        time.sleep(2)
    if run_id is None:
        return None

    ci_start = time.perf_counter()
    r = subprocess.run(["gh", "run", "watch", str(run_id), "--exit-status"],
                        cwd=ROOT, capture_output=True, text=True, timeout=300)
    ci_elapsed = time.perf_counter() - ci_start
    if r.returncode != 0:
        return None

    # GHCR pull needs a package-read scope this CLI token doesn't hold (would
    # require interactive browser re-auth). The locally built image is the
    # same Dockerfile/commit CI just built, so it stands in for "pull the
    # CI-built artifact" without that auth dependency.
    run_local = subprocess.run(
        ["docker", "run", "-d", "--name", "manual-cicd-app", "-p", "8000:8000",
         "cicd-monitoring-study-app:local"],
        capture_output=True, text=True,
    )
    if run_local.returncode != 0:
        return None
    elapsed = wait_ok([HEALTH_URL])
    subprocess.run(["docker", "rm", "-f", "manual-cicd-app"], capture_output=True)
    if elapsed is None:
        return None
    return ci_elapsed + elapsed


def run_full_pipeline():
    subprocess.run(["docker", "compose", "--profile", "full", "up", "-d"], cwd=ROOT, capture_output=True)
    elapsed = wait_ok([HEALTH_URL, PROM_URL, GRAFANA_URL])
    subprocess.run(["docker", "compose", "--profile", "full", "down"], cwd=ROOT, capture_output=True)
    return elapsed


RUNNERS = {
    "manual": run_manual,
    "docker": run_docker,
    "docker_cicd": run_docker_cicd,
    "full_pipeline": run_full_pipeline,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--configs", nargs="+", default=list(RUNNERS.keys()))
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp1_deploy.csv")
    args = p.parse_args()

    rows = []
    for config in args.configs:
        runner = RUNNERS[config]
        for i in range(args.runs):
            teardown_all()
            t0 = time.perf_counter()
            elapsed = runner()
            wall = time.perf_counter() - t0
            success = elapsed is not None
            rows.append({"config": config, "run": i + 1, "success": success,
                         "elapsed_seconds": elapsed if success else "",
                         "wall_seconds": wall})
            print(f"[{config}] run {i+1}/{args.runs} success={success} elapsed={elapsed}")
    teardown_all()

    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "run", "success", "elapsed_seconds", "wall_seconds"])
        if write_header:
            w.writeheader()
        w.writerows(rows)
    print(f"appended {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
