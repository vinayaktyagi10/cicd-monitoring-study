import math
import os
import sys

import pytest
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import stats_lib as sl

A = [1, 2, 3, 4, 5]
B = [3, 4, 5, 6, 7]


def test_mean_ci_matches_t_interval():
    x = [2.1, 2.5, 1.9, 2.8, 2.2, 2.4]
    m, lo, hi = sl.mean_ci(x)
    se = stats.sem(x)
    elo, ehi = stats.t.interval(0.95, len(x) - 1, loc=sum(x) / len(x), scale=se)
    assert m == pytest.approx(sum(x) / len(x))
    assert lo == pytest.approx(elo)
    assert hi == pytest.approx(ehi)


def test_mean_ci_single_value_has_no_interval():
    m, lo, hi = sl.mean_ci([3.0])
    assert m == 3.0 and math.isnan(lo) and math.isnan(hi)


def test_hedges_g_hand_computed():
    assert sl.hedges_g(A, B) == pytest.approx(-1.2649 * (1 - 3 / 31), abs=1e-4)


def test_hedges_g_is_antisymmetric():
    assert sl.hedges_g(B, A) == pytest.approx(-sl.hedges_g(A, B))


def test_hedges_g_ci_contains_point_and_is_ordered():
    g, lo, hi = sl.hedges_g_ci(A, B)
    assert lo < g < hi


def test_cliffs_delta_hand_computed():
    assert sl.cliffs_delta(A, B) == pytest.approx(-0.64)


def test_cliffs_delta_bounds():
    assert sl.cliffs_delta([10, 11], [1, 2]) == 1.0
    assert sl.cliffs_delta([1, 2], [10, 11]) == -1.0
    assert sl.cliffs_delta([1, 2], [1, 2]) == 0.0


def test_welch_matches_scipy():
    r = sl.welch(A, B)
    t, p = stats.ttest_ind(A, B, equal_var=False)
    assert r["t"] == pytest.approx(t)
    assert r["p"] == pytest.approx(p)
    assert r["diff"] == pytest.approx(-2.0)
    assert r["lo"] < -2.0 < r["hi"]


def test_welch_diff_ci_matches_welch_satterthwaite():
    a = [5.1, 4.9, 5.3, 5.0, 5.2, 4.8]
    b = [4.0, 4.6, 3.9, 4.4, 4.1, 4.5, 4.3]
    va, vb = stats.tvar(a) / len(a), stats.tvar(b) / len(b)
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    half = stats.t.ppf(0.975, df) * math.sqrt(va + vb)
    diff = sum(a) / len(a) - sum(b) / len(b)
    r = sl.welch(a, b)
    assert r["df"] == pytest.approx(df)
    assert r["lo"] == pytest.approx(diff - half)
    assert r["hi"] == pytest.approx(diff + half)


def test_wilson_matches_paper_value():
    lo, hi = sl.wilson_ci(7, 8)
    assert round(lo, 3) == 0.529 and round(hi, 3) == 0.978


def test_wilson_all_successes_upper_is_one():
    lo, hi = sl.wilson_ci(20, 20)
    assert hi == pytest.approx(1.0)
    assert lo == pytest.approx(0.8389, abs=1e-4)


def test_bootstrap_ci_is_deterministic_and_brackets_median():
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]
    a = sl.bootstrap_ci(x, stat="median", seed=1)
    b = sl.bootstrap_ci(x, stat="median", seed=1)
    assert a == b
    point, lo, hi = a
    assert point == 5.5
    assert lo <= point <= hi


def test_sample_sd_uses_n_minus_1():
    assert sl.sd([1, 2, 3, 4]) == pytest.approx(stats.tstd([1, 2, 3, 4]))


def test_pearson_ci_fisher_hand_computed():
    lo, hi = sl.fisher_ci(0.5, 28)
    assert lo == pytest.approx(0.1560, abs=1e-3)
    assert hi == pytest.approx(0.7357, abs=1e-3)


def test_pearson_matches_scipy():
    x = [1, 2, 3, 4, 5, 6]
    y = [2.0, 4.1, 5.9, 8.2, 9.8, 12.1]
    r, p, lo, hi = sl.pearson(x, y)
    er, ep = stats.pearsonr(x, y)
    assert r == pytest.approx(er) and p == pytest.approx(ep)
    assert lo < r < hi


def test_did_point_estimate_and_ci():
    a1, b1 = [10, 11, 12, 13], [5, 6, 7, 8]
    a2, b2 = [10, 11, 12, 13], [9, 10, 11, 12]
    point, lo, hi = sl.bootstrap_did(a1, b1, a2, b2, seed=3)
    assert point == pytest.approx((11.5 - 6.5) - (11.5 - 10.5))
    assert lo <= point <= hi
    assert sl.bootstrap_did(a1, b1, a2, b2, seed=3) == (point, lo, hi)


def test_ols_slope_ci_recovers_exact_line():
    x = [0, 1, 2, 3, 4]
    y = [1 + 2 * v for v in x]
    slope, lo, hi, intercept = sl.ols(x, y)
    assert slope == pytest.approx(2.0) and intercept == pytest.approx(1.0)
    assert lo == pytest.approx(2.0) and hi == pytest.approx(2.0)
