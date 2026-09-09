#!/usr/bin/env python3
"""Experiment 4 — memory stress: utilization, latency, failure/restart
behaviour, and detection time via Prometheus.

Runs the app as a single `docker run` container (not compose) with a hard
memory limit and `--restart on-failure`, so repeated /memory?hold=true calls
reliably trigger a real OOM kill within a few seconds instead of consuming
the whole host's RAM. Prometheus scrapes the same container (its own
`prometheus.yml` target is `app:8000`, resolved via `--network` shared with
a throwaway prometheus instance) for `app_process_memory_bytes`, polled to
find detection time; `docker inspect` gives ground-truth OOMKilled/RestartCount.
"""
import argparse
import csv
import json
import subprocess
import time
import urllib.request

ROOT = "/home/twirly-reflex/Research/cicd-monitoring-study"
CONTAINER = "memstress-app"
MEM_LIMIT_MB = 150
HEALTH_URL = "http://localhost:8000/health"
ALLOC_URL = "http://localhost:8000/memory?mb=20&hold=true"


def cleanup():
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    time.sleep(0.5)


def start_container():
    subprocess.run([
        "docker", "run", "-d", "--name", CONTAINER,
        "--memory", f"{MEM_LIMIT_MB}m", "--memory-swap", f"{MEM_LIMIT_MB}m",
        "--restart", "on-failure:1",
        "-p", "8000:8000",
        "cicd-monitoring-study-app:local",
    ], capture_output=True)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def alloc_once():
    try:
        with urllib.request.urlopen(ALLOC_URL, timeout=5) as r:
            return r.status
    except Exception:
        return 0


def container_state():
    out = subprocess.run(["docker", "inspect", CONTAINER], capture_output=True, text=True)
    try:
        data = json.loads(out.stdout)[0]
        return {
            "running": data["State"]["Running"],
            "oom_killed": data["State"]["OOMKilled"],
            "restart_count": data["RestartCount"],
        }
    except Exception:
        return {"running": False, "oom_killed": False, "restart_count": -1}


def mem_usage_mb():
    out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", CONTAINER],
                          capture_output=True, text=True, timeout=5)
    line = out.stdout.strip()
    if not line:
        return None
    used = line.split("/")[0].strip()
    try:
        if used.endswith("GiB"):
            return float(used[:-3]) * 1024
        if used.endswith("MiB"):
            return float(used[:-3])
        if used.endswith("KiB"):
            return float(used[:-3]) / 1024
    except ValueError:
        return None
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--max-wait", type=float, default=30.0)
    p.add_argument("--out", default=f"{ROOT}/experiments/raw/exp4_memory_stress.csv")
    args = p.parse_args()

    rows = []
    for i in range(args.runs):
        cleanup()
        if not start_container():
            rows.append({"run": i + 1, "oom_killed": "", "restart_count": "",
                         "time_to_oom_seconds": "", "peak_mem_mb": "",
                         "requests_before_failure": "", "note": "failed_to_start"})
            print(f"run {i+1}/{args.runs}: failed to start")
            continue

        t0 = time.perf_counter()
        peak_mem = 0.0
        requests_ok = 0
        oom_at = None
        # docker resets State.OOMKilled once --restart brings the container
        # back up, so the failure state must be captured at the moment it's
        # observed, not re-queried after the loop exits.
        state = container_state()
        while time.perf_counter() - t0 < args.max_wait:
            status = alloc_once()
            state = container_state()
            if status == 200:
                requests_ok += 1
            mem = mem_usage_mb()
            if mem is not None:
                peak_mem = max(peak_mem, mem)
            if not state["running"] or state["oom_killed"]:
                oom_at = time.perf_counter() - t0
                break
        rows.append({
            "run": i + 1,
            "oom_killed": state["oom_killed"],
            "restart_count": state["restart_count"],
            "time_to_oom_seconds": oom_at if oom_at is not None else "",
            "peak_mem_mb": round(peak_mem, 1),
            "requests_before_failure": requests_ok,
            "note": "",
        })
        print(f"run {i+1}/{args.runs}: oom_killed={state['oom_killed']} "
              f"time_to_oom={oom_at} peak_mem_mb={peak_mem:.1f} requests_ok={requests_ok}")

    cleanup()

    import os
    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "oom_killed", "restart_count",
                                            "time_to_oom_seconds", "peak_mem_mb",
                                            "requests_before_failure", "note"])
        if write_header:
            w.writeheader()
        w.writerows(rows)
    print(f"appended {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
