#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam
# @Email  : sepinetam@gmail.com
# @File   : stata_info.py

"""Report the Stata runtime environment.

Agents need the Stata version and edition to generate compatible code (frames,
``python``, ``graph dir`` and friends arrived in later releases) and to know
whether the run happens in batch mode, where GUI-only commands are ignored.
"""

import importlib.metadata
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict

from ._runtime import create_runtime_context

INFO_BEGIN = "__STATA_MCP_INFO_BEGIN__"
INFO_END = "__STATA_MCP_INFO_END__"

INFO_KEYS = (
    "stata_version",
    "edition",
    "flavor",
    "os",
    "maxvar",
    "memory",
    "pwd",
    "adopath",
)

_INFO_LINE = re.compile(r"^([a-z_]+)=(.*)$", re.MULTILINE)


def build_probe_dofile() -> str:
    """Build a tiny do-file that prints the environment as ``key=value``."""
    lines = [
        "set linesize 255",
        "set more off",
        f'display "{INFO_BEGIN}"',
    ]
    lines.extend(f'display "{key}=`c({key})\'"' for key in INFO_KEYS)
    lines.append(f'display "{INFO_END}"')
    return "\n".join(lines) + "\n"


def parse_probe_log(log_text: str) -> Dict[str, str]:
    """Extract the ``key=value`` pairs printed by :func:`build_probe_dofile`."""
    match = re.search(
        re.escape(INFO_BEGIN) + r"(.*?)" + re.escape(INFO_END),
        log_text,
        re.DOTALL,
    )
    body = match.group(1) if match else log_text
    values: Dict[str, str] = {}
    for key, value in _INFO_LINE.findall(body):
        if key in INFO_KEYS:
            values[key] = value.strip()
    return values


def _stata_mcp_version() -> str | None:
    for package in ("stata-mcp", "stata_mcp"):
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def stata_info(config_file: str | Path | None = None) -> Dict[str, Any]:
    """Return the Stata version, edition, paths, and batch-mode capabilities."""
    runtime = create_runtime_context(config_file=config_file, require_stata=True)

    from ..stata import StataDo

    probe_path = runtime.tmp_base_path / f"stata_info__{uuid.uuid4().hex}.do"
    probe_path.write_text(build_probe_dofile(), encoding="utf-8")

    executor = StataDo(
        stata_cli=runtime.stata_cli,
        log_file_path=runtime.log_base_path,
        is_unix=runtime.is_unix,
        cwd=runtime.cwd,
        is_wine=runtime.is_wine,
        export_graphs=False,
    )
    try:
        log_paths = executor.execute_dofile(
            probe_path,
            log_file_name="stata_info__probe",
            enable_smcl=False,
        )
        values = parse_probe_log(Path(log_paths["text"]).read_text(encoding="utf-8"))
    except Exception as error:
        logging.error("Failed to read the Stata environment.")
        return {"error": f"Failed to read the Stata environment: {error}"}
    finally:
        probe_path.unlink(missing_ok=True)

    version = values.get("stata_version", "")
    try:
        version_number: int | None = int(version)
    except (TypeError, ValueError):
        version_number = None

    return {
        "stata": values,
        "stata_mcp_version": _stata_mcp_version(),
        "batch_mode": runtime.is_wine or not runtime.is_unix,
        "wine": runtime.is_wine,
        "wine_prefix": (
            runtime.config.WINE_PREFIX.as_posix() if runtime.is_wine else None
        ),
        "supports": {
            "frames": version_number is not None and version_number >= 16,
            "python": version_number is not None and version_number >= 16,
            "graph_capture": runtime.is_wine,
        },
    }
