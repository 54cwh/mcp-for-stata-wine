#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam
# @Email  : sepinetam@gmail.com
# @File   : wine_help.py

"""Local ``.sthlp`` help backend for a Windows Stata driven through Wine.

Batch-mode Stata ignores ``help`` ("request ignored because of batch mode"), so
the Wine profile cannot reuse the pexpect controller. The help files ship with
the installation, so this backend indexes the ado tree inside the Wine prefix
and renders the SMCL source as plain text.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

HELP_SUFFIXES = (".sthlp", ".ihlp", ".hlp")
MAX_SCAN_DEPTH = 6

# Tags whose argument is displayed as literal help text, e.g. ``{depvar}``.
_LITERAL_TAGS = {
    "depvar",
    "indepvars",
    "varname",
    "varlist",
    "newvar",
    "newvarlist",
    "numlist",
    "ifin",
    "weight",
    "exp",
    "tablename",
}

# Structural tags that become whitespace or disappear entirely.
_NEWLINE_TAGS = {"p", "p_end", "break", "line"}
_SPACE_TAGS = {"space", "col"}
_SINGLE_CHAR_TAGS = {"c"}

# ``{opt name:minabbrev}`` renders as name + minabbrev ("nonm"+"issing").
_CONCAT_TAGS = {"opt", "opth"}

# Tags that reference another help topic; the topic name is the display text.
_TOPIC_TAGS = {"help", "helpb", "man", "sthlp", "mansection"}

# Column-layout tags whose content is followed by more text on the same line.
_SPACE_AFTER_TAGS = {"p2col", "synopt", "syntab", "synopthdr"}


def ado_roots(
    prefix: Path | str,
    stata_exe: Path | str | None = None,
    extra_paths: tuple[Path, ...] = (),
) -> list[Path]:
    """Return the ado directories that can hold help files inside a prefix."""
    prefix_path = Path(prefix).expanduser()
    roots: list[Path] = [Path(path).expanduser() for path in extra_paths]

    if stata_exe:
        roots.append(Path(stata_exe).expanduser().parent / "ado")
    else:
        for program_files in ("Program Files", "Program Files (x86)"):
            base = prefix_path / "drive_c" / program_files
            roots.extend(sorted(base.glob("Stata*/ado")))
            roots.extend(sorted(base.glob("StataNow*/ado")))

    users_dir = prefix_path / "drive_c" / "users"
    if users_dir.is_dir():
        for user_ado in users_dir.glob("*/ado"):
            for sub in ("plus", "personal", "updates"):
                roots.append(user_ado / sub)

    unique: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in unique:
            unique.append(root)
    return unique


def _scan(root: Path, depth: int = 0) -> list[Path]:
    if depth > MAX_SCAN_DEPTH:
        return []
    found: list[Path] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        try:
            if entry.is_dir():
                found.extend(_scan(entry, depth + 1))
            elif entry.suffix.lower() in HELP_SUFFIXES:
                found.append(entry)
        except OSError:
            continue
    return found


def build_help_index(roots: list[Path]) -> dict[str, Path]:
    """Map a lower-cased command name to its help file."""
    index: dict[str, Path] = {}
    for root in roots:
        for path in _scan(root):
            index.setdefault(path.stem.lower(), path)
    return index


def build_alias_index(roots: list[Path]) -> dict[str, str]:
    """Parse Stata's ``_help_alias.maint`` abbreviation table."""
    aliases: dict[str, str] = {}
    for root in roots:
        candidate = root / "_" / "_help_alias.maint"
        if not candidate.is_file():
            # ``ado/base/_/_help_alias.maint`` when the root is ``ado``.
            candidate = root / "base" / "_" / "_help_alias.maint"
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    aliases.setdefault(parts[0].lower(), parts[1].lower())
        except OSError as error:
            logger.warning("Failed to read %s: %s", candidate, error)
    return aliases


def _match_brace(text: str, start: int) -> int:
    """Return the index of the ``}`` matching the ``{`` at ``start``."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_tag(body: str) -> tuple[str, str]:
    """Split ``body`` into a lower-cased tag and the remaining arguments."""
    stripped = body.lstrip()
    match = re.match(r"([A-Za-z_][\w-]*)(.*)$", stripped, re.DOTALL)
    if match is None:
        return "", stripped
    return match.group(1).lower(), match.group(2)


def _first_substitution_colon(text: str) -> int:
    """Index of the SMCL ``tag:display`` colon, skipping quotes and nesting."""
    in_quotes = False
    depth = 0
    for index, char in enumerate(text):
        if char == '"':
            in_quotes = not in_quotes
        elif in_quotes:
            continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ":" and depth == 0:
            return index
    return -1


def _render_tag(body: str) -> str:
    tag, rest = _split_tag(body)
    if not tag or tag.startswith("*") or rest.startswith("..."):
        return ""

    rest = rest.lstrip()
    colon = _first_substitution_colon(rest)
    if colon != -1:
        left, right = rest[:colon], rest[colon + 1:]
        if tag in _CONCAT_TAGS:
            # ``{opt nonm:issing}`` -> "nonmissing"; ``{opth vce:(...)}``
            # keeps only the option stem and the inner display text.
            display = re.sub(r"\w+##[^:()\s]*:", "", left.strip() + right)
            return smcl_to_text(display)
        if tag == "title":
            return "\n\n" + smcl_to_text(right) + "\n"
        display = smcl_to_text(right)
        if tag in _SPACE_AFTER_TAGS:
            display += " "
        return display

    if tag in _CONCAT_TAGS:
        return smcl_to_text(rest)
    if tag in _TOPIC_TAGS:
        return smcl_to_text(rest)
    if tag in _LITERAL_TAGS:
        # ``{depvar}`` displays its own name; ``{depvar:x}`` is handled above.
        return smcl_to_text(rest) if rest else tag
    if tag == "title":
        return "\n\n" + smcl_to_text(rest) + "\n"
    if tag in _NEWLINE_TAGS:
        return "\n"
    if tag in _SPACE_TAGS:
        match = re.search(r"\d+", rest)
        return " " * int(match.group()) if match else " "
    if tag == "hline":
        match = re.search(r"\d+", rest)
        return "-" * int(match.group()) if match else ""
    if tag in _SINGLE_CHAR_TAGS:
        return rest.strip()

    # Remaining tags are formatting/structural ({bf}, {p2col}, {marker},
    # {viewer...}); their bare arguments are not help text.
    return ""


def smcl_to_text(source: str) -> str:
    """Render Stata SMCL (``.sthlp``/``.smcl``) into readable plain text."""
    if not source:
        return ""

    parts: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char != "{":
            parts.append(char)
            index += 1
            continue
        end = _match_brace(source, index)
        if end == -1:
            parts.append(char)
            index += 1
            continue
        parts.append(_render_tag(source[index + 1 : end]))
        index = end + 1

    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_INCLUDE_PATTERN = re.compile(
    r"^[ \t]*INCLUDE[ \t]+help[ \t]+(\S+)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_MAX_INCLUDE_DEPTH = 3


class WineStataHelp:
    """Look up help text from the ado tree of a Wine-hosted Stata."""

    def __init__(self, roots: list[Path]):
        self._roots = roots
        self._index: dict[str, Path] | None = None
        self._aliases: dict[str, str] | None = None

    @property
    def index(self) -> dict[str, Path]:
        if self._index is None:
            self._index = build_help_index(self._roots)
        return self._index

    @property
    def aliases(self) -> dict[str, str]:
        if self._aliases is None:
            self._aliases = build_alias_index(self._roots)
        return self._aliases

    def find(self, cmd: str) -> Path | None:
        key = cmd.strip().lower()
        path = self.index.get(key)
        if path is not None:
            return path
        canonical = self.aliases.get(key)
        if canonical is None:
            return None
        return self.index.get(canonical)

    def load(self, cmd: str) -> str | None:
        path = self.find(cmd)
        if path is None:
            return None
        return self._load_path(path, depth=0)

    def _load_path(self, path: Path, depth: int) -> str | None:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            logger.warning("Failed to read help file %s: %s", path, error)
            return None
        return self._expand_includes(smcl_to_text(source), depth)

    def _expand_includes(self, text: str, depth: int) -> str:
        """Inline ``INCLUDE help <topic>`` markers the Stata viewer resolves."""
        if depth >= _MAX_INCLUDE_DEPTH:
            return text

        def replace(match: re.Match[str]) -> str:
            path = self.find(match.group(1))
            if path is None:
                return match.group(0)
            return self._load_path(path, depth + 1) or ""

        return _INCLUDE_PATTERN.sub(replace, text)

    def exists(self, cmd: str) -> bool:
        return self.find(cmd) is not None
