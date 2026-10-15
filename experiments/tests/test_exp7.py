import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import exp7_loaded_overhead as e7


def test_duty_schedule_fractions():
    busy, idle = e7.duty_schedule(40)
    assert abs(busy / (busy + idle) - 0.40) < 1e-9 and abs(busy + idle - e7.PERIOD_S) < 1e-12


def test_duty_schedule_clamps_and_zero():
    assert e7.duty_schedule(0)[0] == 0 and e7.duty_schedule(150)[1] == 0 and e7.duty_schedule(-5)[0] == 0


def test_header_has_burner_and_target_columns():
    assert {"bg_target_pct", "load_burner_cores", "idle_burner_cores"} <= set(e7.FIELDS)
    assert len(e7.FIELDS) == len(set(e7.FIELDS))
