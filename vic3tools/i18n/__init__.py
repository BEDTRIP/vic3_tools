"""Message catalog for command output: English by default, other languages as a layer over it.

Language, first found: ``V3_LANG`` in the environment, ``lang`` in the config, the system locale. A message missing
from a catalog falls back to English.
"""

from __future__ import annotations

import locale
import os
import tomllib
from functools import cache
from importlib import resources

LANGS = ("en", "ru")

_lang: str | None = None


def set_lang(lang: str | None) -> None:
    global _lang
    _lang = lang if lang in LANGS else None


def current_lang() -> str:
    if _lang:
        return _lang
    env = os.environ.get("V3_LANG", "")[:2].lower()
    if env in LANGS:
        return env
    try:
        sys_lang = (locale.getlocale()[0] or "").lower()  # "ru_RU" or, on Windows, "Russian_Russia"
    except ValueError:
        sys_lang = ""
    return "ru" if sys_lang.startswith("ru") else "en"


@cache
def catalog(lang: str) -> dict[str, str]:
    text = resources.files(__package__).joinpath(f"{lang}.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def t(key: str, **kw) -> str:
    """The message ``key`` in the current language, with ``{name}`` placeholders filled."""
    msg = catalog(current_lang()).get(key) or catalog("en").get(key) or key
    return msg.format(**kw) if kw else msg
