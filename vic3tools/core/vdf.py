"""Minimal reader for Valve's text KeyValues format (``libraryfolders.vdf``, ``appmanifest_*.acf``)."""

from __future__ import annotations

import re

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*')


def loads(text: str) -> dict:
    """Parse KeyValues text into nested dicts. Repeated keys: the last one wins."""
    stack: list[dict] = [{}]
    key: str | None = None
    for m in _TOKEN.finditer(text):
        string, brace = m.group(1), m.group(2)
        if string is not None:
            value = string.replace('\\\\', '\\').replace('\\"', '"')
            if key is None:
                key = value
            else:
                stack[-1][key] = value
                key = None
        elif brace == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
    return stack[0]
