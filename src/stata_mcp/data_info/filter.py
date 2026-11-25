#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 - Present Sepine Tam, Inc. All Rights Reserved
#
# @Author : Sepine Tam
# @Email  : sepinetam@gmail.com
# @File   : filter.py

"""Filter rows with a small, safe subset of Stata's ``if`` expressions.

Supports comparisons, ``&``/``|``/``!``, arithmetic, parentheses, string
literals, and the common Stata functions ``missing``, ``inlist``, ``inrange``,
``abs``, ``lower``, ``upper``, and ``strpos``. Expressions are evaluated by
pandas with an empty builtins namespace and identifiers restricted to the
frame's columns plus the function whitelist, so a filter cannot reach Python
internals.
"""

import re
from typing import Any, Iterable, List

import numpy as np
import pandas as pd

ALLOWED_FUNCTIONS: tuple[str, ...] = (
    "missing",
    "inlist",
    "inrange",
    "abs",
    "lower",
    "upper",
    "strpos",
    "ln",
    "log",
    "exp",
    "sqrt",
)

_ALLOWED_CHARS = re.compile(r"""^[\w\s.+\-*/%^&|!~<>=(),"']+$""")
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
_STRING_LITERAL = re.compile(r'"(?:[^"]|"")*"')
_STATA_MISSING = re.compile(r"(?<![\w.])\.(?![\w])")


class FilterError(ValueError):
    """Raised when a filter expression cannot be applied safely."""


def _strip_strings(expression: str) -> str:
    return _STRING_LITERAL.sub('""', expression)


def _normalize(expression: str) -> str:
    expression = expression.strip()
    if not expression:
        raise FilterError("Filter expression is empty.")
    # Stata: ~= is not-equal, ! is not, ^ is power.
    expression = expression.replace("~=", "!=")
    expression = re.sub(r"!(?!=)", "~", expression)
    expression = expression.replace("^", "**")
    return expression


def _validate(expression: str, columns: Iterable[str]) -> None:
    if not _ALLOWED_CHARS.match(expression):
        raise FilterError(
            "Filter contains unsupported characters. Allowed: comparisons, "
            "& | ! ( ), arithmetic, quotes, and named columns."
        )
    bare = _strip_strings(expression)
    if _STATA_MISSING.search(bare):
        raise FilterError(
            "Stata missing values ('.') are not supported in filters; use "
            "missing(column) instead."
        )
    column_set = set(columns)
    allowed = column_set | set(ALLOWED_FUNCTIONS)
    for identifier in _IDENTIFIER.findall(bare):
        if identifier in allowed:
            continue
        raise FilterError(
            f"Unknown identifier {identifier!r} in filter. "
            f"Available columns: {', '.join(sorted(column_set))}."
        )


def _missing(*values: Any) -> Any:
    result = None
    for value in values:
        item = value.isna() if hasattr(value, "isna") else bool(pd.isna(value))
        result = item if result is None else (result | item)
    return result


def _inlist(value: Any, *options: Any) -> Any:
    if hasattr(value, "isin"):
        return value.isin(options)
    return value in options


def _inrange(value: Any, lower: Any, upper: Any) -> Any:
    if hasattr(value, "between"):
        return value.between(lower, upper, inclusive="both")
    return lower <= value <= upper


def _strpos(value: Any, needle: str) -> Any:
    if not hasattr(value, "str"):
        raise FilterError("strpos() requires a string column.")
    return value.str.contains(needle, regex=False, na=False)


def _lower(value: Any) -> Any:
    if not hasattr(value, "str"):
        raise FilterError("lower() requires a string column.")
    return value.str.lower()


def _upper(value: Any) -> Any:
    if not hasattr(value, "str"):
        raise FilterError("upper() requires a string column.")
    return value.str.upper()


_FUNCTION_ENV = {
    "missing": _missing,
    "inlist": _inlist,
    "inrange": _inrange,
    "strpos": _strpos,
    "lower": _lower,
    "upper": _upper,
    "abs": np.abs,
    "ln": np.log,
    "log": np.log,
    "exp": np.exp,
    "sqrt": np.sqrt,
}


def _find_calls(expression: str) -> List[tuple[int, int, str, str]]:
    """Locate ``name(...)`` calls for whitelisted functions."""
    calls: List[tuple[int, int, str, str]] = []
    index = 0
    in_string = False
    while index < len(expression):
        if expression[index] == '"':
            in_string = not in_string
            index += 1
            continue
        if in_string:
            index += 1
            continue
        match = _IDENTIFIER.match(expression, index)
        if match is None:
            index += 1
            continue
        name = match.group()
        cursor = match.end()
        while cursor < len(expression) and expression[cursor].isspace():
            cursor += 1
        if name in ALLOWED_FUNCTIONS and cursor < len(expression) and expression[cursor] == "(":
            end = _match_paren(expression, cursor)
            calls.append((index, end + 1, name, expression[cursor + 1 : end]))
            index = end + 1
            continue
        index = match.end()
    return calls


def _match_paren(expression: str, open_index: int) -> int:
    depth = 0
    in_string = False
    index = open_index
    while index < len(expression):
        char = expression[index]
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    raise FilterError("Unbalanced parentheses in filter expression.")


def _split_args(arguments: str) -> List[str]:
    if not arguments.strip():
        return []
    parts: List[str] = []
    depth = 0
    in_string = False
    start = 0
    for index, char in enumerate(arguments):
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(arguments[start:index].strip())
                start = index + 1
    parts.append(arguments[start:].strip())
    return parts


def _eval_fragment(frame: pd.DataFrame, expression: str) -> Any:
    """Evaluate a scalar/column fragment (arguments of a filter function)."""
    namespace = {column: frame[column] for column in frame.columns}
    try:
        return eval(  # noqa: S307 - validated identifiers, empty builtins
            expression,
            {"__builtins__": {}},
            namespace,
        )
    except Exception as error:
        raise FilterError(
            f"Invalid argument {expression!r} in filter expression: {error}"
        ) from error


def apply_filter(frame: pd.DataFrame, expression: str) -> pd.DataFrame:
    """Return the rows of ``frame`` where ``expression`` is true."""
    normalized = _normalize(expression)
    _validate(normalized, frame.columns)

    local_dict: dict[str, Any] = {column: frame[column] for column in frame.columns}
    # pandas parses comparison/boolean precedence correctly; custom Stata
    # functions are pre-computed and substituted as temporary series.
    for counter, (start, end, name, arguments) in enumerate(
        reversed(_find_calls(normalized))
    ):
        values = [
            _eval_fragment(frame, argument)
            for argument in _split_args(arguments)
        ]
        temp_name = f"_stata_mcp_filter_{counter}"
        local_dict[temp_name] = _FUNCTION_ENV[name](*values)
        normalized = normalized[:start] + temp_name + normalized[end:]

    try:
        mask = frame.eval(
            normalized,
            engine="python",
            resolvers=[local_dict],
            global_dict={"__builtins__": {}},
        )
    except FilterError:
        raise
    except Exception as error:
        raise FilterError(
            f"Invalid filter expression {expression!r}: {error}"
        ) from error

    if isinstance(mask, pd.Series):
        if mask.dtype != bool:
            raise FilterError("Filter must evaluate to a boolean condition.")
        return frame.loc[mask]
    if isinstance(mask, (bool, np.bool_)):
        return frame if bool(mask) else frame.iloc[0:0]
    raise FilterError("Filter must evaluate to a boolean condition.")


def supported_functions() -> List[str]:
    """Return the function names accepted in filter expressions."""
    return list(ALLOWED_FUNCTIONS)
