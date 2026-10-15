import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import reproducibility_table as rp


def row(metric, verdict, rel="-10.0", orig="1.0", rep="0.9"):
    return {"metric": metric, "verdict": verdict, "rel_change_pct": rel, "orig_mean": orig, "rep_mean": rep}


def test_all_consistent_reproduces():
    assert rp.classify([row("a", "CONSISTENT"), row("b", "CONSISTENT")]) == rp.REPRODUCES


def test_all_different_is_environment_dependent():
    assert rp.classify([row("a", "DIFFERENT"), row("b", "DIFFERENT")]) == rp.ENV


def test_mixed_group_is_rejected_not_averaged():
    with pytest.raises(ValueError):
        rp.classify([row("a", "CONSISTENT"), row("b", "DIFFERENT")])


def test_no_values_is_not_classifiable():
    with pytest.raises(ValueError):
        rp.classify([row("a", "NOT RUN")])


def test_ordering_detects_strictly_increasing():
    assert rp.ordered([1.0, 1.4, 1.5], increasing=True)
    assert not rp.ordered([4041, 3996, 4033], increasing=False)
    assert rp.ordered([2737, 2641, 2449], increasing=False)


def test_pct_range_formats_signed_range():
    assert rp.pct_range([row("a", "X", "-28.9"), row("b", "X", "-11.8")]) == r"$-28.9$ to $-11.8$\%"
    assert rp.pct_range([row("a", "X", "47.6")]) == r"$+47.6$\%"


def test_four_statuses_in_fixed_order():
    assert rp.STATUSES == [rp.REPRODUCES, rp.ENV, rp.UNSUPPORTED, rp.INCONCLUSIVE]


def test_excludes_zero_only_when_interval_is_one_sided():
    assert rp.excludes_zero(-158.9, -36.2)
    assert rp.excludes_zero(114, 228)
    assert not rp.excludes_zero(-343.2, 1061.1)
    assert not rp.excludes_zero(-110.2, 1.8)


def test_table_groups_rows_under_status_headings_in_order():
    rows = [("c", rp.INCONCLUSIVE, "z"), ("a", rp.REPRODUCES, "x"), ("b", rp.UNSUPPORTED, "y")]
    lines = rp.build_table(rows).splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("\\multicolumn")]
    assert [lines[i] for i in heads] == [
        f"\\multicolumn{{2}}{{@{{}}l}}{{\\textit{{{s}}}}} \\\\" for s in (rp.REPRODUCES, rp.UNSUPPORTED, rp.INCONCLUSIVE)]
    assert lines.index("a & x \\\\") == heads[0] + 1
    assert lines.index("c & z \\\\") == heads[2] + 1
    assert rp.ENV not in rp.build_table(rows)


def test_unknown_status_is_rejected():
    with pytest.raises(KeyError):
        rp.build_table([("a", "Maybe", "x")])
