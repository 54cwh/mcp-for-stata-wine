"""Tests for doctor checks used with Wine and environment-based CLI config."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from stata_mcp.utils import doctor
from stata_mcp.utils.doctor import CheckStatus, check_stata_execution, check_wine


def _config(tmp_path: Path, **overrides) -> SimpleNamespace:
    values = {
        "IS_WINE": True,
        "IS_UNIX": True,
        "WORKING_DIR": tmp_path,
        "WINE_PREFIX": tmp_path / "prefix",
        "WINE_STATA_EXE": None,
        "STATA_MCP_FOLDER": SimpleNamespace(
            TMP=tmp_path / "tmp",
            LOG=tmp_path / "log",
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_resolve_stata_cli_uses_config_property(monkeypatch, tmp_path: Path):
    cli = tmp_path / "stata-wine"
    cli.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.delenv("STATA_CLI", raising=False)
    config = SimpleNamespace(STATA_CLI=str(cli))

    resolved, source = doctor._resolve_stata_cli(config)

    assert resolved == str(cli)
    assert source == "config"


def test_stata_execution_uses_stata_do(monkeypatch, tmp_path: Path):
    log_file = tmp_path / "doctor.log"

    class FakeStataDo:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def execute_dofile(self, probe, **kwargs):
            log_file.write_text("Stata-MCP Doctor Test\n", encoding="utf-8")
            return {"text": log_file, "success": True, "return_code": 0}

    monkeypatch.setattr("stata_mcp.stata.StataDo", FakeStataDo)

    result = check_stata_execution(_config(tmp_path), "/usr/bin/stata-wine")

    assert result.status is CheckStatus.PASS
    assert result.details["return_code"] == 0


def test_stata_execution_reports_failed_return_code(monkeypatch, tmp_path: Path):
    log_file = tmp_path / "doctor.log"

    class FakeStataDo:
        def __init__(self, **kwargs):
            pass

        def execute_dofile(self, probe, **kwargs):
            log_file.write_text("r(601);\n", encoding="utf-8")
            return {"text": log_file, "success": False, "return_code": 601}

    monkeypatch.setattr("stata_mcp.stata.StataDo", FakeStataDo)

    result = check_stata_execution(_config(tmp_path), "/usr/bin/stata-wine")

    assert result.status is CheckStatus.FAIL
    assert "doctor --check wine" in result.hint


def test_stata_execution_reports_timeout(monkeypatch, tmp_path: Path):
    class FakeStataDo:
        def __init__(self, **kwargs):
            pass

        def execute_dofile(self, probe, **kwargs):
            raise RuntimeError("Stata execution timed out after 15 seconds.")

    monkeypatch.setattr("stata_mcp.stata.StataDo", FakeStataDo)

    result = check_stata_execution(_config(tmp_path), "/usr/bin/stata-wine")

    assert result.status is CheckStatus.FAIL
    assert "timeout" in result.message


def test_wine_check_skips_outside_wine(tmp_path: Path):
    result = check_wine(_config(tmp_path, IS_WINE=False))

    assert result.status is CheckStatus.SKIP


def test_wine_check_fails_on_missing_prefix(tmp_path: Path):
    result = check_wine(_config(tmp_path))

    assert result.status is CheckStatus.FAIL
    assert "prefix" in result.message


def test_wine_check_passes_with_prefix_executable_and_helpers(
    monkeypatch, tmp_path: Path
):
    prefix = tmp_path / "prefix"
    stata_dir = prefix / "drive_c" / "Program Files" / "Stata18"
    stata_dir.mkdir(parents=True)
    (stata_dir / "StataMP-64.exe").write_bytes(b"")

    def fake_which(name):
        return f"/usr/bin/{name}"

    monkeypatch.setattr(doctor.shutil, "which", fake_which)

    result = check_wine(_config(tmp_path))

    assert result.status is CheckStatus.PASS
    assert result.details["stata_exe_exists"] is True


def test_wine_check_warns_without_xvfb(monkeypatch, tmp_path: Path):
    prefix = tmp_path / "prefix"
    stata_dir = prefix / "drive_c" / "Program Files" / "Stata18"
    stata_dir.mkdir(parents=True)
    (stata_dir / "StataMP-64.exe").write_bytes(b"")

    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: None if name == "xvfb-run" else f"/usr/bin/{name}",
    )

    result = check_wine(_config(tmp_path))

    assert result.status is CheckStatus.WARN
