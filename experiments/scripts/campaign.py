#!/usr/bin/env python3
"""Replication campaign: re-runs the paper's experiments with the original,
unmodified scripts plus Experiment 6, into a fresh directory, so the
original raw data in experiments/raw/ is never appended to.

    python experiments/scripts/campaign.py                     # everything except CI/CD
    python experiments/scripts/campaign.py --with-cicd         # also 8 real GitHub Actions runs
    python experiments/scripts/campaign.py --campaign DIR --only e3 e5   # resume / subset

Layout of experiments/replication/<id>/:
  raw/<name>.csv       one file per experiment, same schema as experiments/raw/
  meta/<step>_{before,after}.json   host + software snapshot around every step
  logs/<step>.log      full stdout/stderr of every step
  CAMPAIGN.md          command, timing, exit code and precondition result per step

Before every step the host must pass: Docker networking works (a container
can be started on a bridge network), no other containers are running, ports
8000/8080/9090/3000 are free, and background CPU is below --max-busy-cores.
A failed precondition stops the campaign rather than recording data on a
host in an unknown state. Each step is also appended to experiments/log.md.
"""
import argparse
import datetime
import json
import os
import shlex
import socket
import subprocess
import sys
import time

import hostmetrics
import runmeta

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(SCRIPTS))
PY = sys.executable


def steps(raw, args):
    s = [
        ("e1", f"{PY} {SCRIPTS}/exp1_deploy.py --configs manual docker full_pipeline --runs {args.runs} --out {raw}/exp1_deploy.csv"),
        ("e2", f"{PY} {SCRIPTS}/exp2_resource.py --runs {args.runs} --out {raw}/exp2_resource.csv"),
        ("e3", f"{PY} {SCRIPTS}/exp3_cpu_stress.py --runs {args.runs} --out {raw}/exp3_cpu_stress.csv"),
        ("e4", f"{PY} {SCRIPTS}/exp4_memory_stress.py --runs {args.runs} --out {raw}/exp4_memory_stress.csv"),
        ("e4fill", f"{PY} {SCRIPTS}/exp4_memory_stress.py --fill --runs {args.runs} --out {raw}/exp4_memory_stress_fill.csv"),
        ("e5", f"{PY} {SCRIPTS}/exp5_failure_recovery.py --runs {args.runs} --out {raw}/exp5_failure_recovery.csv"),
        ("e6", f"{PY} {SCRIPTS}/exp6_overhead.py --runs {args.runs} --out {raw}/exp6_overhead.csv"),
        ("e6x4", f"{PY} {SCRIPTS}/exp6_overhead.py --runs {args.runs_e6x4} --cases docker docker_full "
                 f"--loadgen-procs 4 --out {raw}/exp6_overhead_loadgen4.csv"),
    ]
    if args.with_cicd:
        s.insert(1, ("e1cicd", f"{PY} {SCRIPTS}/exp1_deploy.py --configs docker_cicd --runs {args.cicd_runs} "
                               f"--out {raw}/exp1_deploy.csv"))
    return s


def docker_network_ok():
    r = subprocess.run(["docker", "run", "--rm", "cicd-monitoring-study-app:local", "python", "-c", "print(1)"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0, r.stderr.strip()[-300:]


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def busy_cores(seconds=5):
    a = hostmetrics.read_proc_stat()
    time.sleep(seconds)
    return hostmetrics.busy_cores(a, hostmetrics.read_proc_stat())


def preconditions(args):
    problems = []
    ok, err = docker_network_ok()
    if not ok:
        problems.append(f"docker cannot start a networked container: {err}")
    running = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout.split()
    if running:
        problems.append(f"{len(running)} container(s) already running")
    busy = [p for p in (8000, 8080, 9090, 3000) if not port_free(p)]
    if busy:
        problems.append(f"ports in use: {busy}")
    b = busy_cores()
    if b > args.max_busy_cores:
        problems.append(f"background CPU {b:.2f} cores > --max-busy-cores {args.max_busy_cores}")
    return problems, b


def ensure_manual_venv():
    venv = os.path.join(ROOT, ".venv-manual")
    if not os.path.exists(os.path.join(venv, "bin", "python")):
        subprocess.run([PY, "-m", "venv", venv], check=True)
        subprocess.run([f"{venv}/bin/pip", "install", "-q", "-r", f"{ROOT}/app/requirements.txt"], check=True)


def append(path, text):
    with open(path, "a") as fh:
        fh.write(text)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", help="existing campaign dir to resume")
    p.add_argument("--only", nargs="+", help="step ids to run (e1 e1cicd e2 e3 e4 e4fill e5 e6 e6x4)")
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--runs-e6x4", type=int, default=10)
    p.add_argument("--with-cicd", action="store_true")
    p.add_argument("--cicd-runs", type=int, default=8)
    p.add_argument("--cooldown", type=float, default=60.0)
    p.add_argument("--max-busy-cores", type=float, default=0.5)
    args = p.parse_args()

    cid = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    camp = os.path.abspath(args.campaign or os.path.join(ROOT, "experiments", "replication", cid))
    raw, meta, logs = (os.path.join(camp, d) for d in ("raw", "meta", "logs"))
    for d in (raw, meta, logs):
        os.makedirs(d, exist_ok=True)
    report = os.path.join(camp, "CAMPAIGN.md")
    if not os.path.exists(report):
        append(report, f"# Replication campaign {os.path.basename(camp)}\n\nInvocation: "
                       f"`{' '.join(shlex.quote(a) for a in sys.argv)}`\n\n")
    ensure_manual_venv()

    todo = [s for s in steps(raw, args) if not args.only or s[0] in args.only]
    for i, (sid, cmd) in enumerate(todo):
        if i:
            time.sleep(args.cooldown)
        problems, bg = preconditions(args)
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        if problems:
            msg = f"## {stamp} - {sid}: NOT RUN\nPreconditions failed: {'; '.join(problems)}\n\n"
            append(report, msg)
            print(msg)
            sys.exit(2)
        with open(os.path.join(meta, f"{sid}_before.json"), "w") as fh:
            json.dump(runmeta.snapshot(), fh, indent=2)
        print(f"[{stamp}] {sid}: {cmd}", flush=True)
        t0 = time.time()
        with open(os.path.join(logs, f"{sid}.log"), "a") as log:
            proc = subprocess.Popen(shlex.split(cmd), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True)
            for line in proc.stdout:
                sys.stdout.write(line)
                log.write(line)
            rc = proc.wait()
        dur = time.time() - t0
        with open(os.path.join(meta, f"{sid}_after.json"), "w") as fh:
            json.dump(runmeta.snapshot(), fh, indent=2)
        rel = os.path.relpath(camp, ROOT)
        append(report, f"## {stamp} - {sid}\nCommand: `{cmd}`\nExit code: {rc}, duration {dur / 60:.1f} min, "
                       f"background CPU before start {bg:.2f} cores\nLog: logs/{sid}.log\n\n")
        append(os.path.join(ROOT, "experiments", "log.md"),
               f"\n## {stamp} - Replication campaign {os.path.basename(camp)}, step {sid}\n"
               f"Command: `{cmd}`\nRaw: {rel}/raw/ ; log: {rel}/logs/{sid}.log ; "
               f"host snapshot: {rel}/meta/{sid}_before.json\n"
               f"Notes: exit code {rc}, {dur / 60:.1f} min, background CPU {bg:.2f} cores at start "
               f"(written automatically by campaign.py).\n")
        if rc != 0:
            print(f"{sid} exited {rc}; stopping")
            sys.exit(rc)
    print(f"campaign complete: {camp}\nnext: make validate CAMPAIGN={os.path.relpath(camp, ROOT)}")


if __name__ == "__main__":
    main()
