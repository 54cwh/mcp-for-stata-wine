#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam
# @Email  : sepinetam@gmail.com
# @File   : api/read_log.py

import logging
from pathlib import Path
from typing import Literal

from ..stata import StataLog

logger = logging.getLogger(__name__)


def read_log(
    file_path: str,
    encoding: str = "utf-8",
    *,
    output_format: Literal["full", "core", "dict"] = "core",
    pattern: str | None = None,
    context: int = 0,
    config_file: str | Path | None = None,
) -> str:
    """Read a Stata log file as a direct one-shot utility."""
    from ._runtime import create_runtime_context

    runtime = create_runtime_context(config_file=config_file)

    path = Path(file_path).expanduser().resolve()

    if runtime.config.STRICT_READ_LOG_BOUNDARY:
        allowed_dirs = (
            runtime.config.STATA_MCP_FOLDER.path,
            *getattr(runtime.config, "ADDITIONAL_ALLOWED_DIRS", ()),
        )
        is_allowed = False
        for allowed_dir in allowed_dirs:
            try:
                path.relative_to(allowed_dir.resolve())
                is_allowed = True
                break
            except ValueError:
                continue
        if not is_allowed:
            logger.warning(
                "[SECURITY VIOLATION] read_log outside allowed directory: %s",
                path,
            )
            return "Access denied: log file must be within the stata-mcp folder."

    if not path.exists():
        raise FileNotFoundError(f"The file at {file_path} does not exist.")

    from ..stata.builtin_tools.stata_log.search import search_entries, search_text

    def finish(text: str) -> str:
        return search_text(text, pattern, context) if pattern else text

    if not runtime.config.ENABLE_STRUCTURED_LOG:
        return finish(path.read_text(encoding=encoding))

    if path.suffix.lower() not in {".log", ".smcl"}:
        return finish(path.read_text(encoding=encoding))

    log_reader = StataLog.from_path(path, encoding=encoding)
    if output_format == "full":
        return finish(log_reader.read_plain_text())
    if output_format == "core":
        return finish(log_reader.read_without_framework())
    if output_format == "dict":
        dict_data = log_reader.read_as_dict()
        if pattern:
            entries = search_entries(
                dict_data.get("command_result_list", []), pattern
            )
            if not entries:
                return f"No log entries matched pattern {pattern!r}."
            dict_data["command_result_list"] = entries
        return str(dict_data)
    raise ValueError(f"Invalid output_format: {output_format}")
