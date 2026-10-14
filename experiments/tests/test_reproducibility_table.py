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
