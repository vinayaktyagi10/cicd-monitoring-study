"""Interval estimates and effect sizes used by validate.py and
analyze_overhead.py. Sample statistics throughout (ddof=1); the paper's
summary tables use population std (pstdev), which this module never does.
"""
import math
import random
import statistics

from scipy import stats as _st


def sd(x):
    return statistics.stdev(x)


def mean_ci(x, conf=0.95):
    x = list(x)
    m = statistics.mean(x)
    if len(x) < 2:
        return m, float("nan"), float("nan")
    half = _st.t.ppf((1 + conf) / 2, len(x) - 1) * sd(x) / math.sqrt(len(x))
    return m, m - half, m + half


def welch(a, b, conf=0.95):
    a, b = list(a), list(b)
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se = math.sqrt(va + vb)
    diff = statistics.mean(a) - statistics.mean(b)
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    t = diff / se
    p = 2 * _st.t.sf(abs(t), df)
    half = _st.t.ppf((1 + conf) / 2, df) * se
    return {"diff": diff, "lo": diff - half, "hi": diff + half, "t": t, "df": df, "p": p}


def hedges_g(a, b):
    a, b = list(a), list(b)
    n1, n2 = len(a), len(b)
    pooled = math.sqrt(((n1 - 1) * statistics.variance(a) + (n2 - 1) * statistics.variance(b)) / (n1 + n2 - 2))
    if pooled == 0:
        return float("nan")
    d = (statistics.mean(a) - statistics.mean(b)) / pooled
    return d * (1 - 3 / (4 * (n1 + n2) - 9))


def hedges_g_ci(a, b, conf=0.95):
    g = hedges_g(a, b)
    n1, n2 = len(a), len(b)
    se = math.sqrt((n1 + n2) / (n1 * n2) + g**2 / (2 * (n1 + n2)))
    z = _st.norm.ppf((1 + conf) / 2)
    return g, g - z * se, g + z * se


def cliffs_delta(a, b):
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def mann_whitney_p(a, b):
    return _st.mannwhitneyu(a, b, alternative="two-sided").pvalue


def wilson_ci(successes, n, z=1.96):
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denom
    return centre - half, centre + half


def bootstrap_ci(x, stat="median", n_boot=10000, conf=0.95, seed=0):
    fn = {"median": statistics.median, "mean": statistics.mean}[stat]
    x = list(x)
    rng = random.Random(seed)
    boots = sorted(fn(rng.choices(x, k=len(x))) for _ in range(n_boot))
    lo_i = int(n_boot * (1 - conf) / 2)
    hi_i = int(n_boot * (1 + conf) / 2) - 1
    return fn(x), boots[lo_i], boots[hi_i]


def fisher_ci(r, n, conf=0.95):
    if n <= 3 or abs(r) >= 1:
        return float("nan"), float("nan")
    z = math.atanh(r)
    half = _st.norm.ppf((1 + conf) / 2) / math.sqrt(n - 3)
    return math.tanh(z - half), math.tanh(z + half)


def pearson(x, y, conf=0.95):
    r, p = _st.pearsonr(x, y)
    lo, hi = fisher_ci(r, len(x), conf)
    return float(r), float(p), lo, hi


def ols(x, y, conf=0.95):
    res = _st.linregress(x, y)
    half = _st.t.ppf((1 + conf) / 2, len(x) - 2) * res.stderr
    return res.slope, res.slope - half, res.slope + half, res.intercept


def bootstrap_did(a1, b1, a2, b2, n_boot=10000, conf=0.95, seed=0):
    def did(w, x, y, z):
        return (statistics.mean(w) - statistics.mean(x)) - (statistics.mean(y) - statistics.mean(z))

    groups = [list(a1), list(b1), list(a2), list(b2)]
    rng = random.Random(seed)
    boots = sorted(did(*(rng.choices(g, k=len(g)) for g in groups)) for _ in range(n_boot))
    return did(*groups), boots[int(n_boot * (1 - conf) / 2)], boots[int(n_boot * (1 + conf) / 2) - 1]
