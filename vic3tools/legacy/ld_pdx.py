"""Top-level records of Paradox scripts with exact bounds -- the old names (``ld_pdx``) over ``vic3tools.core.script``:
``read`` gives (text, had a BOM, line end), ``write`` writes with a BOM by default.
"""
from vic3tools.core import script as _s

DIRECTIVES, OPS, TOKEN = _s.DIRECTIVES, _s.OPS, _s.TOKEN
Tok, Entry = _s.Tok, _s.Entry
tokens, split_directive, parse, block_items, norm = _s.tokens, _s.split_directive, _s.parse, _s.block_items, _s.norm
_lead = _s._lead


def read(path):
    """(текст без BOM, был_ли_BOM, перевод строки файла)."""
    return tuple(_s.read(path))


def write(path, text, bom=True, eol="\n"):
    _s.write(path, text, bom=bom, eol=eol)
