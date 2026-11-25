"""Tests for the Stata-style row filter used by get_data_info."""

import pandas as pd
import pytest

from stata_mcp.data_info.csv import CsvDataInfo
from stata_mcp.data_info.filter import FilterError, apply_filter


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "price": [3000, 5000, 8000, 9000],
            "foreign": [0, 1, 1, 0],
            "make": ["VW", "BMW", "Audi", "Ford"],
            "rep78": [3, None, 5, 2],
        }
    )


@pytest.mark.parametrize(
    ("expression", "expected_rows"),
    [
        ("price > 4000", 3),
        ("foreign == 1 & price > 6000", 1),
        ("foreign == 1 | price > 8500", 3),
        ("missing(rep78)", 1),
        ("!missing(rep78) & foreign == 1", 1),
        ("inlist(foreign, 1)", 2),
        ("inrange(price, 4000, 8000)", 2),
        ('make == "BMW"', 1),
        ('strpos(make, "Au")', 1),
        ('lower(make) == "vw"', 1),
        ("abs(price - 5000) < 100", 1),
        ("price^2 > 60000000", 2),
    ],
)
def test_apply_filter_matches_stata_semantics(frame, expression, expected_rows):
    assert len(apply_filter(frame, expression)) == expected_rows


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo pwn')",
        "price == .",
        "price[0] > 1",
        "unknown_column > 1",
        "price >",
    ],
)
def test_apply_filter_rejects_unsafe_or_invalid_expression(frame, expression):
    with pytest.raises(FilterError):
        apply_filter(frame, expression)


def test_data_info_applies_filter_and_offset(tmp_path):
    csv_path = tmp_path / "cars.csv"
    pd.DataFrame(
        {"price": [10, 20, 30, 40], "group": [1, 1, 2, 2]}
    ).to_csv(csv_path, index=False)

    info = CsvDataInfo(
        csv_path,
        head=1,
        offset=1,
        filter_expr="group == 2",
        is_cache=False,
    )
    result = info.info

    assert result["overview"]["obs"] == 2
    assert result["overview"]["obs_before_filter"] == 4
    assert result["overview"]["preview_offset"] == 1
    assert result["head"][0]["price"] == 40
