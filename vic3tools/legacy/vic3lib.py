"""Reading and writing Vic3 scripts for the projects' generators -- the old names (``vic3lib``) over
``vic3tools.core.script``: ``read`` gives the text without BOM and with LF, ``write`` decides the BOM by the content
(``bom=None``) and writes through a temporary file; ``sub`` / ``sub_span`` / ``replace_sub`` / ``entry`` -- blocks
by key.
"""
from vic3tools.core import script as _s

sha = _s.sha
entry = _s.entry
sub_names = _s.sub_names
brace_balance = _s.brace_balance
_depth0_iter = _s.depth0_iter


def read(path):
    """Текст файла без BOM, CRLF → LF; битый UTF-8 — ошибка."""
    return _s.read_text(path)


def write(path, text, bom=None):
    """bom=None — BOM, если вне комментариев есть не-ASCII (правила, раздел 11); запись через временный файл."""
    _s.write(path, text, bom=bom)


def sub(body, name, level=1):
    return _s.sub(body, name)


def sub_span(body, name, level=1):
    return _s.sub_span(body, name)


def replace_sub(body, name, new_block, level=1):
    return _s.replace_sub(body, name, new_block)


def _match_brace(s, i):
    """i — индекс '{'; индекс парной '}' (комментарии и строки не мешают)."""
    toks = _s.tokens(s, i)
    j = _s._close(toks, 0)
    if j >= len(toks):
        raise ValueError(f'unbalanced braces from offset {i}')
    return toks[j].pos
