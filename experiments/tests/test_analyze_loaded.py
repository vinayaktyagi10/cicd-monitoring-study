import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import analyze_loaded as al


def rows(penalty_by_level, n=15, base=6000.0, sd=20.0, seed=3):
    rng = random.Random(seed)
    out = []
    for lv, pen in penalty_by_level.items():
        for case in ("docker", "docker_full"):
            for _ in range(n):
                tp = base - (pen if case == "docker_full" else 0) + rng.gauss(0, sd)
                out.append({"case": case, "bg_target_pct": float(lv), "throughput_ok_rps": tp,
                            "load_host_busy_cores": lv / 100 * 16, "load_burner_cores": lv / 100 * 16 - 0.1,
                            "load_monitoring_cores": 0.03 if case == "docker_full" else 0.0})
    return out


def test_contrast_reports_penalty_as_docker_minus_full():
    g = al.group(rows({0: 0, 60: 120}))
    c = {x["level"]: x for x in al.contrasts(g)}
    assert abs(c[60]["penalty"] - 120) < 25 and abs(c[0]["penalty"]) < 25
    assert c[60]["lo"] > 0 and c[60]["lo"] < c[60]["penalty"] < c[60]["hi"]


def test_did_detects_a_penalty_that_grows_with_load():
    g = al.group(rows({0: 0, 20: 40, 40: 80, 60: 120}))
    d = al.did(g, 0, 60)
    assert d["did"] > 60 and d["lo"] > 0


def test_did_contains_zero_when_penalty_is_flat():
    g = al.group(rows({0: 30, 60: 30}))
    d = al.did(g, 0, 60)
    assert d["lo"] < 0 < d["hi"]


def test_verdict_only_supported_when_interval_excludes_zero_upward():
    assert al.verdict({"lo": 10.0, "hi": 90.0}) == "supported"
    assert al.verdict({"lo": -40.0, "hi": 60.0}) == "not supported"
    assert al.verdict({"lo": -90.0, "hi": -10.0}) == "reversed"


def test_achieved_load_reports_measured_means_per_level():
    a = {x["level"]: x for x in al.achieved(rows({0: 0, 60: 0}))}
    assert abs(a[60]["host_busy_cores"] - 9.6) < 1e-9
