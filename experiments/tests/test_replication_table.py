import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import replication_table as rt

ROW = {"exp": "E2", "metric": "App CPU%, Docker", "orig_mean": "11.0151", "orig_ci_lo": "9.466",
       "orig_ci_hi": "12.564", "rep_mean": "7.4153", "rep_ci_lo": "6.373", "rep_ci_hi": "8.458",
       "rel_change_pct": "-32.7", "verdict": "DIFFERENT"}
NOT_RUN = {"exp": "E4", "metric": "Time to OOM (s)", "orig_mean": "", "orig_ci_lo": "", "orig_ci_hi": "",
           "rep_mean": "", "rep_ci_lo": "", "rep_ci_hi": "", "rel_change_pct": "", "verdict": "NOT RUN"}


def test_row_escapes_latex_specials_and_formats_intervals():
    line = rt.format_row(ROW)
    assert line == (r"App CPU\%, Docker & 11.02 [9.47, 12.56] & 7.42 [6.37, 8.46] & $-32.7$ & different \\")


def test_not_run_row_shows_dashes():
    assert rt.format_row(NOT_RUN) == r"Time to OOM (s) & --- & --- & --- & not run \\"


def test_table_has_booktabs_rules_and_one_line_per_row():
    t = rt.build_table([ROW, NOT_RUN])
    assert t.count(r"\midrule") == 1 and r"\toprule" in t and r"\bottomrule" in t
    assert t.count(r"\\") == 3
