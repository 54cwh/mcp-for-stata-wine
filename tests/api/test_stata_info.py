"""Tests for the Stata environment probe (no Stata process required)."""

from stata_mcp.api.stata_info import (
    INFO_KEYS,
    build_probe_dofile,
    parse_probe_log,
)


def test_probe_do_file_prints_every_key() -> None:
    probe = build_probe_dofile()

    for key in INFO_KEYS:
        assert f'`c({key})' in probe
    assert "set linesize 255" in probe


def test_parse_probe_log_reads_values_and_ignores_command_echo() -> None:
    log = """
. do "Z:/tmp/stata_info__abc.do"

. display "__STATA_MCP_INFO_BEGIN__"
__STATA_MCP_INFO_BEGIN__

. display "stata_version=`c(stata_version)'"
stata_version=18

. display "edition=`c(edition)'"
edition=BE

. display "pwd=`c(pwd)'"
pwd=Z:\\tmp\\project

. display "__STATA_MCP_INFO_END__"
__STATA_MCP_INFO_END__
"""

    values = parse_probe_log(log)

    assert values["stata_version"] == "18"
    assert values["edition"] == "BE"
    assert values["pwd"] == "Z:\\tmp\\project"


def test_parse_probe_log_returns_empty_when_markers_missing() -> None:
    assert parse_probe_log("nothing here\nregress price mpg") == {}
