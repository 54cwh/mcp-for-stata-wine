#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam
# @Email  : sepinetam@gmail.com
# @File   : search.py

"""Search Stata logs for a pattern, with optional surrounding context."""

import re
from typing import Iterable, List


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def search_text(text: str, pattern: str, context: int = 0) -> str:
    """Return matching lines with ``line_number: text`` prefixes.

    ``context`` adds that many lines before and after each match; overlapping
    windows are merged and separated with ``--``.
    """
    if not pattern:
        return text

    context = max(int(context), 0)
    matcher = _compile(pattern)
    lines = text.splitlines()
    windows: List[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if matcher.search(line):
            start = max(index - context, 0)
            end = min(index + context, len(lines) - 1)
            if windows and start <= windows[-1][1] + 1:
                windows[-1] = (windows[-1][0], max(windows[-1][1], end))
            else:
                windows.append((start, end))

    if not windows:
        return f"No lines matched pattern {pattern!r}."

    rendered: List[str] = []
    for start, end in windows:
        if rendered:
            rendered.append("--")
        rendered.extend(f"{number}: {lines[number - 1]}" for number in range(start + 1, end + 2))
    return "\n".join(rendered)


def search_entries(
    entries: Iterable[dict], pattern: str
) -> List[dict]:
    """Filter ``command_result`` dict entries whose command or result matches."""
    if not pattern:
        return list(entries)
    matcher = _compile(pattern)
    matched: List[dict] = []
    for entry in entries:
        haystack = " ".join(
            str(entry.get(key, "")) for key in ("command", "result")
        )
        if matcher.search(haystack):
            matched.append(entry)
    return matched
