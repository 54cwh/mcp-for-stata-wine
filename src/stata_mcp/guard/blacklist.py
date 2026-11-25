#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam (谭淞)
# @Email  : sepinetam@gmail.com
# @File   : blacklist.py

"""Stata dofile security blacklist definitions.

This module defines dangerous commands and patterns that should be blocked
when executing Stata dofiles, unless dangerous mode is explicitly enabled.
"""

from typing import List, Set, Tuple

# ============================================================================
# Stata Command Prefixes
# ============================================================================

#: Stata prefixes that can precede commands and must be stripped before
#: validation. Includes full names and minimum abbreviations.
STATA_PREFIXES: Tuple[str, ...] = (
    "capture",
    "cap",
    "quietly",
    "qui",
    "noisily",
    "noi",
    "by",
    "byable",
    "sort",
)

# ============================================================================
# Dangerous Commands
# ============================================================================

#: Package-management commands that must only run through the controlled
#: ado-package installation API, never through arbitrary dofiles.
PACKAGE_MANAGEMENT_COMMANDS: Set[str] = {
    "ssc",
    "net",
    "github",
    "adoupdate",
    "update",
}

#: Commands that allow execution of shell/system commands
DANGEROUS_COMMANDS: Set[str] = {
    "!",          # Unix-style shell escape: !ls
    "!!",         # Extended shell command (xshell synonym): !!vi file.do
    "shell",      # Shell command execution: shell dir
    "sh",         # Stata abbreviation for shell
    "xshell",     # Extended shell for Mac/Unix(GUI): xshell vi file.do
    "xsh",        # Stata abbreviation for xshell
    "winexec",    # Windows program execution: winexec notepad.exe
    "winex",      # Stata abbreviation for winexec
    "unixcmd",    # Unix command execution: unixcmd ls
    "unixc",      # Stata abbreviation for unixcmd
    "erase",      # File deletion command
    "era",        # Stata abbreviation for erase
    "rmdir",      # Directory removal command
    "rmd",        # Stata abbreviation for rmdir
    "python",     # Python execution block: python:
    "mata",       # Mata execution block
    "java",       # Java integration
    "plugin",     # Native plugin loading
}


# ============================================================================
# Dangerous Patterns (Regular Expressions)
# ============================================================================

#: Patterns that may indicate dangerous operations
DANGEROUS_PATTERNS: List[str] = [
    # Shell command execution (must be at line start)
    r"^\s*!\s*\w+",           # Shell escape with command: ! ls, !dir
    r"^\s*!!\s*\w+",          # Extended shell with command: !! vi file.do
    r"^\s*shell\s+\w+",       # Shell command: shell dir, shell ls
    r"^\s*xshell\s+\w+",      # Extended shell: xshell vi file.do
    r"^\s*winexec\s+\S+",     # Windows execution: winexec program.exe
    r"^\s*unixcmd\s+\w+",     # Unix command: unixcmd ls

    # File operations (must be at line start to avoid false positives)
    r"^\s*erase\s+",          # File deletion: erase file.dta
    r"^\s*rm\s+",             # File deletion (alias): rm file.dta
    r"^\s*rmdir\s+",          # Directory removal: rmdir mydir
    r"^\s*copy\s+",           # File copy (can overwrite): copy file1.dta file2.dta

    # Code execution from external files (must be at line start)
    r"^\s*run\s+",            # Run another do-file: run script.do
    r"^\s*do\s+",             # Run another do-file: do script.do
    r"^\s*include\s+",        # Include another do-file: include setup.do

    # Embedded language/runtime execution
    r"^\s*python\s*:",        # Python block execution: python:
    r"^\s*mata\b",            # Mata execution
    r"^\s*java\b",            # Java integration
    r"^\s*plugin\b",          # Native plugin loading
]


# ============================================================================
# Batch-Mode No-Ops
# ============================================================================

#: GUI-only commands that Stata silently ignores in batch mode ("request
#: ignored because of batch mode"). Running them wastes a run and leaves the
#: agent believing it inspected the data, so batch profiles reject them with a
#: pointer to the MCP tool that covers the same need.
_BATCH_IGNORED_ALIASES: dict[str, tuple[str, ...]] = {
    "browse": ("br", "bro", "brow", "brows", "browse"),
    "edit": ("ed", "edi", "edit"),
    "view": ("vi", "vie", "view"),
    "doedit": ("doe", "doed", "doedi", "doedit"),
    "help": ("help",),
    "search": ("sear", "searc", "search"),
    "findit": ("findit",),
    "db": ("db",),
    "window": ("window", "win"),
}

BATCH_IGNORED_COMMANDS: dict[str, str] = {
    alias: command
    for command, aliases in _BATCH_IGNORED_ALIASES.items()
    for alias in aliases
}

BATCH_IGNORED_HINTS: dict[str, str] = {
    "browse": "use the get_data_info tool to inspect the dataset",
    "edit": "batch mode cannot edit data; make the change in the do-file",
    "view": "batch mode has no viewer; open the file in your editor",
    "doedit": "batch mode has no do-file editor; edit the file directly",
    "help": "use the help tool to read documentation",
    "search": "use the help tool or the documentation instead",
    "findit": "use the help tool or search the web instead",
    "db": "dialog boxes are unavailable in batch mode",
    "window": "window management is unavailable in batch mode",
}


# ============================================================================
# Metadata
# ============================================================================

__all__ = [
    "BATCH_IGNORED_COMMANDS",
    "BATCH_IGNORED_HINTS",
    "DANGEROUS_COMMANDS",
    "DANGEROUS_PATTERNS",
    "PACKAGE_MANAGEMENT_COMMANDS",
    "STATA_PREFIXES",
]
