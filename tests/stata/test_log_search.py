"""Tests for log pattern search used by read_log."""

from pathlib import Path

from stata_mcp.api.read_log import read_log
from stata_mcp.stata.builtin_tools.stata_log.search import search_entries, search_text


def test_search_text_returns_matching_lines_with_context():
    text = "header\n. regress price mpg\nr(111);\n. summarize\nfooter"

    result = search_text(text, r"r\(\d+\)", context=1)

    assert "2: . regress price mpg" in result
    assert "3: r(111);" in result
    assert "4: . summarize" in result
    assert "header" not in result


def test_search_text_merges_overlapping_windows():
    text = "a\nERROR one\nb\nERROR two\nc"

    result = search_text(text, "ERROR", context=1)

    assert result.count("--") == 0
    assert "1: a" in result and "5: c" in result


def test_search_text_reports_no_matches():
    assert search_text("nothing here", "xyz") == "No lines matched pattern 'xyz'."


def test_search_text_falls_back_to_literal_for_invalid_regex():
    text = "value is (unclosed"

    result = search_text(text, "(unclosed")

    assert "1: value is (unclosed" in result


def test_search_entries_filters_command_results():
    entries = [
        {"command": "regress price mpg", "result": "ok"},
        {"command": "summarize", "result": "r(111) error"},
    ]

    assert search_entries(entries, "r\\(111\\)") == [entries[1]]


def test_api_read_log_applies_pattern(tmp_path: Path):
    log = tmp_path / "run.log"
    log.write_text(". regress price mpg\nr(111);\n. summarize\n", encoding="utf-8")

    result = read_log(str(log), pattern="r\\(111\\)", context=1)

    assert "2: r(111);" in result
    assert "1: . regress price mpg" in result
