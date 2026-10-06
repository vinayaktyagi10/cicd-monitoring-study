#!/usr/bin/env python3
"""Snapshot of everything about the host and software that could change a
measurement: git state, kernel, CPU power settings, background CPU load,
Docker/Compose versions, image IDs and digests, Python packages.

    python runmeta.py --out meta.json
"""
import argparse
import datetime
import glob
import json
import os
import platform
import subprocess
import sys
import time

import hostmetrics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGES = ["cicd-monitoring-study-app:local", "gcr.io/cadvisor/cadvisor:v0.49.1",
          "prom/prometheus:v2.55.1", "grafana/grafana:11.2.0"]


def sh(*cmd, cwd=ROOT):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def cpu_model():
    for line in (read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()


def power():
    supplies = {}
    for d in glob.glob("/sys/class/power_supply/*"):
        online = read(os.path.join(d, "online"))
        if online is not None:
            supplies[os.path.basename(d)] = online
    return {
        "platform_profile": read("/sys/firmware/acpi/platform_profile"),
        "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "energy_performance_preference": read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"),
        "boost": read("/sys/devices/system/cpu/cpufreq/boost"),
        "power_supply_online": supplies,
    }


def background_load(seconds=3.0):
    a = hostmetrics.read_proc_stat()
    time.sleep(seconds)
    b = hostmetrics.read_proc_stat()
    return {"busy_cores": round(hostmetrics.busy_cores(a, b), 3), "window_s": seconds,
            "loadavg": os.getloadavg(),
            "top_processes": sh("ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu").splitlines()[:12]}


def images():
    out = {}
    for img in IMAGES:
        raw = sh("docker", "image", "inspect", img)
        try:
            d = json.loads(raw)[0]
            out[img] = {"id": d["Id"], "repo_digests": d.get("RepoDigests"), "created": d.get("Created")}
        except Exception:
            out[img] = None
    return out


def snapshot():
    return {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "git": {"commit": sh("git", "rev-parse", "HEAD"), "branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
                "status_porcelain": sh("git", "status", "--porcelain").splitlines()},
        "host": {"hostname": platform.node(), "kernel": platform.release(), "running_kernel_modules_present":
                 os.path.isdir(f"/lib/modules/{platform.release()}"), "cpu_model": cpu_model(),
                 "logical_cpus": os.cpu_count(), "mem_total_kb": (read("/proc/meminfo") or "").splitlines()[0],
                 "os_release": dict(l.split("=", 1) for l in (read("/etc/os-release") or "").splitlines() if "=" in l)
                 .get("PRETTY_NAME")},
        "power": power(),
        "background": background_load(),
        "docker": {"server": sh("docker", "version", "--format", "{{.Server.Version}}"),
                   "compose": sh("docker", "compose", "version", "--short"),
                   "info": sh("docker", "info", "--format",
                              "{{.CgroupDriver}} cgroup-v{{.CgroupVersion}} {{.Driver}} {{.KernelVersion}}"),
                   "running_containers": sh("docker", "ps", "--format", "{{.Names}}").splitlines(),
                   "images": images()},
        "python": {"executable": sys.executable, "version": sys.version,
                   "packages": sh(sys.executable, "-m", "pip", "freeze").splitlines()},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args()
    meta = snapshot()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"wrote {args.out}: busy_cores={meta['background']['busy_cores']} "
          f"profile={meta['power']['platform_profile']} kernel={meta['host']['kernel']}")


if __name__ == "__main__":
    main()
