import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import thp_stride_table as ts


def row(stride, killed, blocks, split, m=409):
    nz = 512 // stride if stride else 0
    return {"stride": str(stride), "zero_subpages": str(512 - nz), "max_ptes_none": str(m),
            "oom_killed": str(killed), "blocks_reached": str(blocks), "d_thp_underused_split_page": str(split)}


ROWS = [row(0, False, 20, 170), row(0, False, 98, 160), row(4, True, 7, 0), row(4, True, 7, 1),
        row(5, True, 13, 70), row(5, False, 20, 160)]


def test_groups_by_stride_in_ascending_order_with_zero_fill_first():
    assert [c["stride"] for c in ts.summarize(ROWS)] == [0, 4, 5]


def test_underused_prediction_follows_max_ptes_none():
    cells = {c["stride"]: c for c in ts.summarize(ROWS)}
    assert cells[0]["predicted"] and not cells[4]["predicted"] and cells[5]["predicted"]


def test_blocks_are_capped_at_the_block_limit():
    assert ts.summarize(ROWS)[0]["blocks"] == 20


def test_counts_kills_and_split_range():
    c = {c["stride"]: c for c in ts.summarize(ROWS)}
    assert (c[4]["killed"], c[4]["n"], c[4]["splits"]) == (2, 2, (0, 1))
    assert (c[5]["killed"], c[5]["n"]) == (1, 2)


def test_table_has_one_line_per_stride():
    t = ts.build_table(ROWS)
    assert t.count(r"\\") == 4 and r"\toprule" in t
