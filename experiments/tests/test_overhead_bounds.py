import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import analyze_overhead as ao


def rows(penalty, n=20, base=6000.0, block_sd=200.0, run_sd=20.0, seed=5):
    rng = random.Random(seed)
    out = []
    for b in range(1, n + 1):
        shared = rng.gauss(0, block_sd)
        for case in ("docker", "docker_full"):
            out.append({"case": case, "pinned": False, "loadgen_procs": 1, "block": float(b),
                        "throughput_ok_rps": base + shared - (penalty if case == "docker_full" else 0)
                        + rng.gauss(0, run_sd),
                        "load_monitoring_cores": 0.03 if case == "docker_full" else 0.0})
    return out


def test_contrast_reports_percent_interval_scaled_by_baseline_mean():
    c = ao.contrasts(ao.cells(rows(90)))[0]
    base = sum(r["throughput_ok_rps"] for r in rows(90) if r["case"] == "docker") / 20
    assert abs(c["pct_lo"] - 100 * c["diff_lo"] / base) < 1e-9
    assert abs(c["pct_hi"] - 100 * c["diff_hi"] / base) < 1e-9
    assert c["pct_lo"] < c["pct_change"] < c["pct_hi"]


def test_blocked_contrast_is_tighter_than_independent_when_blocks_drift():
    cs = ao.cells(rows(90))
    ind = ao.contrasts(cs)[0]
    blk = ao.blocked_contrasts(cs)[0]
    assert (blk["diff_hi"] - blk["diff_lo"]) < 0.3 * (ind["diff_hi"] - ind["diff_lo"])
    assert blk["diff_lo"] < -90 < blk["diff_hi"]
    assert blk["n_blocks"] == 20


def test_blocked_contrast_uses_only_blocks_where_both_cases_ran():
    r = rows(90)
    r = [x for x in r if not (x["case"] == "docker_full" and x["block"] == 3.0)]
    blk = ao.blocked_contrasts(ao.cells(r))[0]
    assert blk["n_blocks"] == 19


def test_blocked_contrast_contains_zero_without_a_penalty():
    blk = ao.blocked_contrasts(ao.cells(rows(0)))[0]
    assert blk["diff_lo"] < 0 < blk["diff_hi"]
