import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import thp_vm_table as tv


def row(thp, shrink, mpn, stride, killed, n_reps=1):
    return [{"thp_enabled": thp, "shrink_underused": str(shrink), "max_ptes_none": str(mpn), "stride": str(stride),
             "oom_killed": str(killed)} for _ in range(n_reps)]


ROWS = (row("always", 1, 409, 0, False, 3) + row("always", 1, 511, 0, True, 3) + row("madvise", 1, 409, 0, True, 3)
        + row("always", 1, 409, 4, True, 3))


def test_only_the_zero_fill_stride_is_summarized():
    cells = tv.summarize(ROWS)
    assert sum(n for v in cells.values() for _, n in v.values()) == 9


def test_cells_are_keyed_by_policy_and_shrinker_with_a_count_per_threshold():
    cells = tv.summarize(ROWS)
    assert cells[("always", 1)] == {409: (0, 3), 511: (3, 3)}
    assert cells[("madvise", 1)] == {409: (3, 3)}


def test_table_has_a_header_and_one_row_per_policy_and_shrinker_pair():
    t = tv.build_table(ROWS)
    assert t.count("\\\\") == 1 + 2
    assert "0/3" in t and "3/3" in t


def test_table_keeps_only_the_default_and_distro_thresholds():
    t = tv.build_table(ROWS + row("always", 1, 200, 0, False, 3))
    assert "200" not in t and "409" in t and "511" in t
