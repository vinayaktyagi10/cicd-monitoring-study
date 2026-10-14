import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import thp_table as tt


def row(fill, off, killed, blocks, split):
    return {"fill": str(fill), "thp_disabled_for_probe": str(off), "oom_killed": str(killed),
            "blocks_reached": str(blocks), "d_thp_underused_split_page": str(split)}


ROWS = [row(False, False, False, 20, 169), row(False, False, False, 20, 171),
        row(False, True, True, 7, 0), row(False, True, True, 7, 0),
        row(True, False, True, 7, 1), row(True, False, True, 7, 0),
        row(True, True, True, 7, 0), row(True, True, True, 7, 0)]


def test_groups_into_four_cells_in_fixed_order():
    cells = tt.summarize(ROWS)
    assert [c["label"] for c in cells] == ["Zero-filled", "Zero-filled", "Non-zero", "Non-zero"]
    assert [c["thp"] for c in cells] == ["default", "disabled", "default", "disabled"]


def test_counts_kills_median_blocks_and_split_range():
    zero_default = tt.summarize(ROWS)[0]
    assert (zero_default["killed"], zero_default["n"]) == (0, 2)
    assert zero_default["blocks"] == 20 and zero_default["splits"] == (169, 171)
    assert tt.summarize(ROWS)[1]["killed"] == 2


def test_table_is_booktabs_with_one_line_per_cell():
    t = tt.build_table(ROWS)
    assert t.count(r"\\") == 5 and r"\toprule" in t and r"0/2" in t and r"2/2" in t
