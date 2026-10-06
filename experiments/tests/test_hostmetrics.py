import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import hostmetrics as hm

PROC_STAT_1 = """cpu  100 0 50 800 50 0 0 0 30 0
cpu0 50 0 25 400 25 0 0 0 15 0
cpu1 50 0 25 400 25 0 0 0 15 0
intr 12345
ctxt 999
"""
PROC_STAT_2 = """cpu  250 0 100 1550 100 0 0 0 90 0
cpu0 125 0 50 775 50 0 0 0 45 0
cpu1 125 0 50 775 50 0 0 0 45 0
intr 12399
"""

CPU_STAT = """usage_usec 2500000
user_usec 2000000
system_usec 500000
nr_periods 0
"""


def test_parse_proc_stat_counts_cpus_and_excludes_guest():
    s = hm.parse_proc_stat(PROC_STAT_1)
    assert s.ncpu == 2
    assert s.total == 1000
    assert s.busy == 150


def test_busy_cores_from_two_snapshots():
    a, b = hm.parse_proc_stat(PROC_STAT_1), hm.parse_proc_stat(PROC_STAT_2)
    assert hm.busy_cores(a, b) == pytest.approx(2 * 200 / 1000)


def test_busy_cores_zero_interval():
    a = hm.parse_proc_stat(PROC_STAT_1)
    assert hm.busy_cores(a, a) == 0.0


def test_parse_cpu_stat_usage():
    assert hm.parse_cpu_stat(CPU_STAT) == 2_500_000


def test_cgroup_cores():
    assert hm.cgroup_cores(1_000_000, 3_000_000, 4.0) == pytest.approx(0.5)


def test_cgroup_candidates_cover_systemd_and_cgroupfs_drivers():
    paths = hm.cgroup_candidates("abc123")
    assert "/sys/fs/cgroup/system.slice/docker-abc123.scope" in paths
    assert "/sys/fs/cgroup/docker/abc123" in paths
