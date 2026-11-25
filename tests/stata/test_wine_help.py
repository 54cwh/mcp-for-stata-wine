"""Tests for the local .sthlp help backend used under Wine."""

from pathlib import Path

from stata_mcp.stata.builtin_tools.help.stata_help import StataHelp
from stata_mcp.stata.builtin_tools.help.wine_help import (
    ado_roots,
    build_alias_index,
    build_help_index,
    smcl_to_text,
)


def test_smcl_renders_syntax_tags_as_readable_text():
    source = (
        "{smcl}\n"
        "{title:Syntax}\n"
        "{synopt :{opt nocons}}suppress constant term{p_end}\n"
        "{synopt :{opt l:evel(#)}}set confidence level{p_end}\n"
        "{marker options}\n"
        "See {help regress##weight:weight} for details.\n"
    )

    text = smcl_to_text(source)

    assert "Syntax" in text
    assert "nocons suppress constant term" in text
    assert "level(#)" in text
    assert "See weight for details." in text
    assert "{marker" not in text


def test_smcl_drops_comments_and_structural_tags():
    source = "{* internal note}{...}{p2colset 1 16 18 2}{p2colreset}{hline 10}\nBody"

    text = smcl_to_text(source)

    assert "internal note" not in text
    assert "p2col" not in text
    assert "Body" in text


def test_help_index_and_alias_resolution(tmp_path: Path):
    base = tmp_path / "ado" / "base" / "_"
    base.mkdir(parents=True)
    (base / "_help_alias.maint").write_text("reg\trregress\n", encoding="utf-8")
    help_dir = tmp_path / "ado" / "base" / "r"
    help_dir.mkdir(parents=True)
    (help_dir / "regress.sthlp").write_text(
        "{title:Syntax}\n{opt regress} {depvar}\n", encoding="utf-8"
    )

    roots = [tmp_path / "ado"]
    index = build_help_index(roots)
    aliases = build_alias_index(roots)

    assert index["regress"] == help_dir / "regress.sthlp"
    assert aliases["reg"] == "rregress"


def test_stata_help_uses_wine_backend_without_a_controller(tmp_path: Path):
    help_dir = tmp_path / "ado" / "base" / "r"
    help_dir.mkdir(parents=True)
    (help_dir / "regress.sthlp").write_text(
        "{title:Regress}\n{opt regress} {depvar}\n", encoding="utf-8"
    )
    reader = StataHelp(
        stata_cli=None,
        project_tmp_dir=tmp_path / "tmp",
        cache_dir=tmp_path / "cache",
        help_roots=[tmp_path / "ado"],
    )

    assert reader.controller is None
    assert "regress" in reader.load_from_stata("regress").lower()
    assert reader.check_command_exist_with_help("regress") is True
    assert reader.check_command_exist_with_help("nosuchcmd") is False


def test_stata_help_reports_missing_wine_help(tmp_path: Path):
    help_dir = tmp_path / "ado" / "base" / "r"
    help_dir.mkdir(parents=True)
    reader = StataHelp(
        project_tmp_dir=tmp_path / "tmp",
        cache_dir=tmp_path / "cache",
        help_roots=[tmp_path / "ado"],
    )

    try:
        reader.load_from_stata("nosuchcmd")
    except Exception as error:
        assert "No help found" in str(error)
    else:
        raise AssertionError("missing help should raise")


def test_ado_roots_finds_install_and_user_ado(tmp_path: Path):
    program_files = tmp_path / "drive_c" / "Program Files" / "Stata18"
    (program_files / "ado").mkdir(parents=True)
    user_ado = tmp_path / "drive_c" / "users" / "cwh" / "ado"
    (user_ado / "plus").mkdir(parents=True)

    roots = ado_roots(tmp_path)

    assert program_files / "ado" in roots
    assert user_ado / "plus" in roots


def test_ado_roots_includes_extra_help_paths(tmp_path: Path):
    custom_ado = tmp_path / "project-ado"
    custom_ado.mkdir()

    roots = ado_roots(tmp_path / "prefix", extra_paths=(custom_ado,))

    assert custom_ado in roots
