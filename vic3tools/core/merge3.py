"""
Three-way merge for Victoria 3 script records.

Why this exists (written for the TGR x VC patch of vic3_mods): TGR and VC both rebuild the same
vanilla records. Doing the merge by eye means re-reading a 1000-line interest group per record and re-doing it on
every update of either mod. Vanilla is the common ancestor of both, so the merge
is a plain three-way: take every hunk that only one side touched, and fall back
to a declared winner where both touched the same lines.

Conflicts are NOT silently resolved -- merge3() returns them, and the callers in
regen_vc_tgr.py print every one. A conflict that is not read is a lost edit.

Line granularity, not token: the mods edit whole lines (a value plus a trailing
"#TGR CHANGES" comment), so a finer diff would only produce noise.
"""

from __future__ import annotations

import difflib


def hunks(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    """Changes of `other` against `base`, in base coordinates: (i1, i2, replacement)."""
    sm = difflib.SequenceMatcher(None, base, other, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            out.append((i1, i2, other[j1:j2]))
    return out


def _overlap(a, b) -> bool:
    """A pure insertion never conflicts.

    This is a judgement about these two mods, not a general truth. VC's additions
    are flavour content TGR has never seen -- amendments, journal entries,
    modifiers -- and they routinely land inside a region TGR deleted (France: TGR
    drops four vanilla laws, VC inserts five amendments in the middle of them).
    Calling that a conflict and picking a winner threw away one author's whole
    contribution. Applying both is what both authors meant.

    Two replacements of overlapping ranges are a real conflict: there the authors
    are writing over each other's lines."""
    a1, a2 = a[0], a[1]
    b1, b2 = b[0], b[1]
    if a1 == a2 or b1 == b2:
        return False
    return a1 < b2 and b1 < a2


def _rebuild(base, lo, hi, cluster):
    out = []
    pos = lo
    for i1, i2, rep in sorted(cluster):
        out.extend(base[pos:i1])
        out.extend(rep)
        pos = i2
    out.extend(base[pos:hi])
    return out


_ASSIGN = __import__("re").compile(r"^\s*([A-Za-z0-9_.:\-]+)\s*(?:\?=|>=|<=|!=|=|>|<)")


def _keys(lines) -> list[str]:
    """Left-hand sides assigned or compared in these lines, in order.

    Comparisons count, not just assignments: `scope:number > 3` and
    `scope:number = 3` are two authors arguing about the same thing, and stacking
    them inside one `limit` yields a condition that is never true."""
    out = []
    for line in lines:
        m = _ASSIGN.match(line.split("#", 1)[0])
        if m:
            out.append(m.group(1))
    return out


def _balance(lines) -> int:
    total = 0
    for line in lines:
        code = line.split("#", 1)[0]
        total += code.count("{") - code.count("}")
    return total


def _both(base, lo, hi, ca, cb):
    """Union of two competing rewrites of the same base lines, or None.

    Right where both mods dropped the same vanilla line and each put its own
    content in its place (China: both drop `set_variable = ryukyu_rival_member`,
    one adds a company, the other seven journal entries) -- there the union is
    what both authors meant.

    Wrong where they edited the SAME line differently (Britain: `ig:ig_intelligentsia = {`
    against `ig:ig_intelligentsia ?= {`) -- the union emits the line twice and the
    braces stop matching. That case is detected here rather than guessed at: if the
    union does not have the same brace balance as both sides, return None and let
    the caller fall back to a declared winner."""
    seg = base[lo:hi]
    text_a = _rebuild(base, lo, hi, ca)
    text_b = _rebuild(base, lo, hi, cb)

    added = []
    for _i1, _i2, rep in hunks(seg, text_b):
        added.extend(rep)

    # Guard 1: A's version and what B puts in assign the same field. Then they are
    # competing values, not independent content, and appending both applies both:
    # `multiply = 2.0` followed by `multiply = 2` multiplies twice, and a `limit`
    # holding both `scope:number > 3` and `scope:number = 3` can never be true.
    # Nothing in the log either way.
    if set(_keys(text_a)) & set(_keys(added)):
        return None

    # Guard 2: bare list members (a line with no `=`, e.g. a building name inside
    # `building_types`) may only be appended when A left the block structure alone.
    # East India Company: A closes `building_types` and opens
    # `extension_building_types`; appending B's `building_sugar_plantation` after
    # that silently files the building under the wrong list, braces still matching.
    a_has_braces = any("{" in ln.split("#", 1)[0] or "}" in ln.split("#", 1)[0] for ln in text_a)
    if a_has_braces:
        for line in added:
            code = line.split("#", 1)[0].strip()
            if code and "=" not in code:
                return None

    out = text_a + added
    if _balance(added) != 0:
        return None
    if _balance(out) == _balance(text_a) == _balance(text_b):
        return out
    return None


def merge3(base, a, b, prefer="b"):
    """Merge `a` and `b` over their common ancestor `base`.

    prefer: who wins a cluster both sides REPLACED -- "a", "b", or "both"
    (union, see _both).
    Returns (merged_lines, conflicts), conflicts = [(lo, hi, a_text, b_text, how)]
    in base coordinates, so the caller can print exactly what it decided. `how` is
    the resolution actually used, which is not always `prefer`: a "both" cluster
    that cannot be unioned safely falls back to "b".
    """
    ha = sorted(hunks(base, a))
    hb = sorted(hunks(base, b))
    out: list[str] = []
    conflicts = []
    pos = ia = ib = 0

    while ia < len(ha) or ib < len(hb):
        A = ha[ia] if ia < len(ha) else None
        B = hb[ib] if ib < len(hb) else None

        if A is not None and B is not None and _overlap(A, B):
            # Both sides made the identical edit (typically the REPLACE_OR_CREATE:
            # prefix line, or a change both authors copied from a shared source).
            # Applying it once is not a conflict.
            if A == B:
                start = max(pos, A[0])
                out.extend(base[pos:start])
                out.extend(A[2])
                pos = max(pos, A[1])
                ia += 1
                ib += 1
                continue
            lo, hi = min(A[0], B[0]), max(A[1], B[1])
            ca, cb = [A], [B]
            ia += 1
            ib += 1
            grew = True
            while grew:                      # a cluster can pull in further hunks
                grew = False
                while ia < len(ha) and ha[ia][0] < hi:
                    ca.append(ha[ia])
                    lo = min(lo, ha[ia][0])
                    hi = max(hi, ha[ia][1])
                    ia += 1
                    grew = True
                while ib < len(hb) and hb[ib][0] < hi:
                    cb.append(hb[ib])
                    lo = min(lo, hb[ib][0])
                    hi = max(hi, hb[ib][1])
                    ib += 1
                    grew = True
            start = max(pos, lo)
            out.extend(base[pos:start])
            how = prefer
            chunk = _both(base, lo, hi, ca, cb) if prefer == "both" else None
            if chunk is None:
                how = "b" if prefer == "both" else prefer
                chunk = _rebuild(base, lo, hi, ca if how == "a" else cb)
            out.extend(chunk)
            conflicts.append((lo, hi, _rebuild(base, lo, hi, ca), _rebuild(base, lo, hi, cb), how))
            pos = max(pos, hi)
        else:
            # Not a conflict: apply whichever hunk comes first. max(pos, ...)
            # matters because an insertion can sit inside a range the other side
            # already replaced -- without it `pos` walks backwards and duplicates
            # the base lines in between.
            H = A if (B is None or (A is not None and A[0] <= B[0])) else B
            start = max(pos, H[0])
            out.extend(base[pos:start])
            out.extend(H[2])
            pos = max(pos, H[1])
            if H is A:
                ia += 1
            else:
                ib += 1

    out.extend(base[pos:])
    return out, conflicts


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8-sig", errors="strict") as fh:
        return fh.read().replace("\r\n", "\n").split("\n")


def brace_balance(text: str) -> int:
    total = 0
    for line in text.split("\n"):
        line = line.split("#", 1)[0]
        total += line.count("{") - line.count("}")
    return total


def needs_bom(text: str) -> bool:
    """BOM is required when a NON-comment line carries a byte above 127.
    ASCII art and Chinese comments in a header do not count."""
    for line in text.split("\n"):
        code = line.split("#", 1)[0]
        if any(ord(ch) > 127 for ch in code):
            return True
    return False
