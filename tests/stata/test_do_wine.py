"""Unit tests for the Wine execution path (``STATA_MCP__IS_WINE``).

A Wine-hosted Stata is a Windows GUI binary: it ignores stdin (so the unix
executor cannot drive it) and resolves POSIX paths written inside a do-file
against ``C:``, failing with r(603). ``_execute_wine`` therefore launches an
argv list without a shell and rewrites every path to Wine's ``Z:`` notation
while keeping the returned log path POSIX so ``read_log`` keeps working.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from stata_mcp.stata.stata_do.do import StataDo


class _FakePopen:
    returncode = 0

    def communicate(self, timeout=None):
        return ("", "")

    def poll(self):
        return 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


@pytest.fixture
def dofile(tmp_path: Path) -> Path:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    path = work_dir / "wine check.do"
    path.write_text("display 42\n")
    return path


@pytest.fixture
def executor(tmp_path: Path) -> StataDo:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return StataDo(
        stata_cli="/usr/local/bin/stata-wine",
        log_file_path=log_dir,
        is_unix=True,
        cwd=tmp_path,
        is_wine=True,
    )


def _batch_path(cmd: list[str]) -> Path:
    """Strip Wine's ``Z:`` prefix from the batch path in argv."""
    assert cmd[3].startswith("Z:/")
    return Path(cmd[3][2:])


class TestToWinePath:
    def test_translates_absolute_posix_path(self):
        assert StataDo._to_wine_path("/tmp/a.do") == "Z:/tmp/a.do"

    def test_preserves_spaces_and_returns_str(self):
        result = StataDo._to_wine_path("/tmp/x y/a.do")

        assert result == "Z:/tmp/x y/a.do"
        assert isinstance(result, str)

    def test_rejects_non_posix_path(self, monkeypatch):
        monkeypatch.setattr(Path, "resolve", lambda self: Path("C:/windows/x.do"))

        with pytest.raises(ValueError, match="absolute POSIX path"):
            StataDo._to_wine_path("C:/windows/x.do")


class TestExecuteWineBeatsUnix:
    def test_wine_branch_wins_over_unix(self, monkeypatch, executor, dofile):
        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen",
            lambda cmd, **kwargs: _FakePopen(),
        )
        unix_called = []
        monkeypatch.setattr(
            StataDo,
            "_execute_unix_like",
            lambda self, *a, **k: unix_called.append(True),
        )

        executor.execute_dofile(dofile, log_file_name="wine_wins")

        assert unix_called == []


class TestExecuteWineCommand:
    def test_argv_has_no_shell_and_z_paths(
        self, monkeypatch, executor, dofile, tmp_path
    ):
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["kwargs"] = kwargs
            captured["batch"] = _batch_path(cmd)
            captured["wrapper"] = captured["batch"].read_text(encoding="utf-8")
            return _FakePopen()

        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen", fake_popen
        )

        result = executor.execute_dofile(dofile, log_file_name="wine_run")

        cmd = captured["cmd"]
        assert cmd[0] == "/usr/local/bin/stata-wine"
        assert cmd[1:3] == ["/e", "do"]
        assert cmd[3].endswith(".do")
        assert captured["kwargs"]["shell"] is False
        assert captured["kwargs"]["cwd"] == tmp_path
        assert captured["kwargs"]["text"] is True

        wrapper = captured["wrapper"]
        assert 'log using "Z:/' in wrapper
        assert 'do "Z:/' in wrapper

    def test_returns_posix_log_path(self, monkeypatch, executor, dofile):
        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen",
            lambda cmd, **kwargs: _FakePopen(),
        )

        result = executor.execute_dofile(dofile, log_file_name="wine_run")

        assert result["text"] == executor.log_file_path / "wine_run.log"
        assert result["text"].is_absolute()
        assert "Z:" not in str(result["text"])

    def test_removes_batch_file_after_run(self, monkeypatch, executor, dofile):
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["batch"] = _batch_path(cmd)
            return _FakePopen()

        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen", fake_popen
        )

        executor.execute_dofile(dofile, log_file_name="wine_run")

        assert not captured["batch"].exists()


class TestExecuteWineFailures:
    def test_nonzero_returncode_raises_with_stderr(
        self, monkeypatch, executor, dofile
    ):
        captured = {}
        process = Mock(returncode=1)
        process.communicate.return_value = ("", "r(603) file not found")

        def fake_popen(cmd, **kwargs):
            captured["batch"] = _batch_path(cmd)
            return process

        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen", fake_popen
        )

        with pytest.raises(RuntimeError, match=r"r\(603\) file not found"):
            executor.execute_dofile(dofile, log_file_name="wine_fail")

        assert not captured["batch"].exists()

    def test_timeout_raises_and_removes_batch_file(
        self, monkeypatch, executor, dofile
    ):
        captured = {}
        process = Mock()
        process.communicate.side_effect = subprocess.TimeoutExpired("stata-wine", 3)
        process.poll.side_effect = [None, 0]
        process.wait.return_value = 0

        def fake_popen(cmd, **kwargs):
            captured["batch"] = _batch_path(cmd)
            return process

        monkeypatch.setattr(
            "stata_mcp.stata.stata_do.do.subprocess.Popen", fake_popen
        )

        with pytest.raises(RuntimeError, match="timed out after 3 second"):
            executor.execute_dofile(dofile, log_file_name="wine_timeout", timeout=3)

        assert not captured["batch"].exists()
        process.terminate.assert_called_once_with()
