import glob
import hashlib
import os

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMPAIGN = os.path.join(EXP, "replication", "2026-10-06_1653", "raw")
NAMES = ["exp6_overhead.csv", "exp6_overhead_loadgen4.csv", "exp6_overhead_keepalive.csv",
         "exp6_overhead_keepalive_loadgen4.csv", "diag_timewait.csv", "diag_thp.csv"]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@pytest.mark.parametrize("name", NAMES)
def test_e6_raw_matches_campaign_copy(name):
    assert sha(os.path.join(EXP, "raw", name)) == sha(os.path.join(CAMPAIGN, name))
