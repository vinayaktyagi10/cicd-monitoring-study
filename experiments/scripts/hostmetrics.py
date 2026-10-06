"""Kernel-counter CPU accounting over an exact time window: whole host from
/proc/stat, each container from its cgroup v2 cpu.stat. Unlike a
`docker stats --no-stream` snapshot, two reads bracket precisely the
interval being measured.
"""
import os
import subprocess
from collections import namedtuple

ProcStat = namedtuple("ProcStat", "busy total ncpu")


def parse_proc_stat(text):
    busy = total = ncpu = 0
    for line in text.splitlines():
        if line.startswith("cpu "):
            f = [int(v) for v in line.split()[1:9]]
            total = sum(f)
            busy = total - f[3] - f[4]
        elif line.startswith("cpu"):
            ncpu += 1
    return ProcStat(busy, total, ncpu)


def read_proc_stat():
    with open("/proc/stat") as fh:
        return parse_proc_stat(fh.read())


def busy_cores(before, after):
    dt = after.total - before.total
    if dt <= 0:
        return 0.0
    return after.ncpu * (after.busy - before.busy) / dt


def parse_cpu_stat(text):
    for line in text.splitlines():
        k, _, v = line.partition(" ")
        if k == "usage_usec":
            return int(v)
    raise ValueError("usage_usec not found")


def cgroup_cores(usage_before, usage_after, wall_seconds):
    return (usage_after - usage_before) / 1e6 / wall_seconds


def cgroup_candidates(container_id):
    return [
        f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope",
        f"/sys/fs/cgroup/docker/{container_id}",
    ]


def container_cgroup(name):
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", name],
                         capture_output=True, text=True, check=True).stdout.strip()
    for path in cgroup_candidates(cid):
        if os.path.exists(os.path.join(path, "cpu.stat")):
            return path
    raise FileNotFoundError(f"no cgroup v2 cpu.stat for {name} ({cid[:12]})")


def read_cgroup_usage(path):
    with open(os.path.join(path, "cpu.stat")) as fh:
        return parse_cpu_stat(fh.read())


def read_cgroup_mem_mb(path):
    with open(os.path.join(path, "memory.current")) as fh:
        return int(fh.read()) / (1024 * 1024)
