#!/usr/bin/env python3
"""Drift diagnostic -- does the laptop power profile explain the 27% throughput gap between
Experiment 6 (AC, platform profile performance) and Experiment 7 (battery, balanced)?

Runs the Experiment 6/7 keep-alive Docker-only measurement (app only, 10 s settle, 20 s
closed-loop load at concurrency 10) in blocks; the platform profile is switched by hand
(Fn+Q) between blocks in the order balanced, performance, balanced, performance, so the profile
is not confounded with time. Per run it records the power state read back from sysfs
(platform profile, governor, EPP, boost, AC), mean CPU frequency over the load window (all CPUs,
sampled every 0.5 s) and the k10temp Tctl temperature before, at peak and after.
Refuses to run on battery or if the profile is not the one the block expects.

    python diag_power.py --block 1 --expect balanced [--runs 6] [--out experiments/raw/diag_power.csv]
"""
import argparse
import csv
import datetime
import glob
import os
import statistics
import threading
import time

import exp6_overhead as e6

ROOT = e6.ROOT
FIELDS = ["timestamp", "block", "run", "expected_profile", "platform_profile", "governor", "epp", "boost",
          "ac_online", "throughput_ok_rps", "errors", "p95_latency_ms", "mean_freq_mhz", "max_freq_mhz",
          "tctl_before_c", "tctl_max_c", "tctl_after_c", "load_wall_s"]


def read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def hwmon(name):
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(f"{d}/name") == name:
            return d
    return None


K10 = hwmon("k10temp")


def tctl():
    return int(read(f"{K10}/temp1_input")) / 1000 if K10 else float("nan")


def state():
    cpu0 = "/sys/devices/system/cpu/cpu0/cpufreq"
    return {"platform_profile": read("/sys/firmware/acpi/platform_profile"),
            "governor": read(f"{cpu0}/scaling_governor"), "epp": read(f"{cpu0}/energy_performance_preference"),
            "boost": read("/sys/devices/system/cpu/cpufreq/boost"),
            "ac_online": read("/sys/class/power_supply/ACAD/online")}


def mean_freq_mhz():
    vals = [int(read(p)) for p in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq") if read(p)]
    return statistics.mean(vals) / 1000


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.freqs, self.temps, self.stop = [], [], threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.freqs.append(mean_freq_mhz())
            self.temps.append(tctl())
            self.stop.wait(0.5)


def one_run(args):
    e6.teardown()
    e6.bring_up(["app"])
    time.sleep(args.settle)
    before = tctl()
    s = Sampler()
    s.start()
    t0 = time.perf_counter()
    ok, errors = e6.run_load(args.duration, args.concurrency, keepalive=True)
    wall = time.perf_counter() - t0
    s.stop.set()
    s.join()
    return {"throughput_ok_rps": len(ok) / wall, "errors": errors, "p95_latency_ms": e6.pct(ok, 0.95),
            "mean_freq_mhz": statistics.mean(s.freqs), "max_freq_mhz": max(s.freqs),
            "tctl_before_c": before, "tctl_max_c": max(s.temps), "tctl_after_c": tctl(), "load_wall_s": wall}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--block", type=int, required=True)
    p.add_argument("--expect", required=True, help="platform profile this block must run under")
    p.add_argument("--runs", type=int, default=6)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--settle", type=float, default=10.0)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--out", default=os.path.join(ROOT, "experiments", "raw", "diag_power.csv"))
    args = p.parse_args()
    st = state()
    if st["ac_online"] != "1":
        raise SystemExit("on battery: plug in AC")
    if st["platform_profile"] != args.expect:
        raise SystemExit(f"platform profile is {st['platform_profile']!r}, block expects {args.expect!r}")
    new = not os.path.exists(args.out)
    for i in range(1, args.runs + 1):
        row = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "block": args.block, "run": i,
               "expected_profile": args.expect, **state(), **one_run(args)}
        with open(args.out, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if new:
                w.writeheader()
                new = False
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()})
        print(f"block {args.block} run {i}: {row['platform_profile']}/{row['governor']}/{row['epp']} "
              f"{row['throughput_ok_rps']:7.0f} rps  freq {row['mean_freq_mhz']:5.0f} MHz  "
              f"Tctl {row['tctl_before_c']:.0f}->{row['tctl_max_c']:.0f} C", flush=True)
    e6.teardown()


if __name__ == "__main__":
    main()
