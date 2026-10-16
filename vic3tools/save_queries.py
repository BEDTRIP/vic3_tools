"""Questions to a text save: variables, who owns the levels, buildings of a type, a company's buildings, a goods' flows.

The general versions of the projects' save scripts (``save_ownership``, ``save_ownership_transfers``,
``scan_building_type``, ``scan_company_buildings``, ``scan_save_vars``, ``scan_goods_io``) over ``vic3tools.save``.

Save facts used here (1.13):

- ``building_manager`` entries: ``building``, ``levels``, ``state`` (``4294967295`` — a removed building whose record
  stays), weekly ``goods_sales`` / ``goods_cost`` / ``profit_after_reserves``; ``input_goods`` / ``output_goods`` —
  ``goods={ <goods id>={ value=… } }``, units a week.
- ``building_ownership_manager`` entries: ``levels``, ``identity={ building=<owner building> }`` or
  ``identity={ country=<id> }`` (the state), ``building=<owned building>``; ``privatization=yes`` marks a level on sale.
  The owner building is a manor house (aristocrats), a financial district (capitalists), a company HQ or a regional HQ.
- ``companies`` entries: ``country``, ``building`` (its HQ building), ``company_type``.
- Script variables: ``variables={ data={ { flag=<name> data={ type=value identity=<n> } } … } }`` — a value is
  ``identity / 100000``, negative ones are written as unsigned 64-bit; ``type=ctry`` is a country id; maps:
  ``name="<map>" list={ { key={…} value={…} } … }``.
"""

from __future__ import annotations

import fnmatch
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from vic3tools.save import Block, Save, number

DEAD_STATE = "4294967295"
DIV = 100000
OWNER_BUILDINGS = {"building_manor_house": "manor", "building_financial_district": "findist"}
# Not production: owner buildings, the army, ports, urban centres, the government (their levels are not "owned").
NONPROD = {"building_manor_house", "building_financial_district", "building_barrack", "building_conscription_center",
           "building_construction_regulator", "building_trade_center", "building_government_administration",
           "building_port", "building_river_port", "building_university", "building_urban_center",
           "building_army_logistics_center"}
NONPROD_PREFIX = ("building_naval_", "building_company_", "building_regional_company_",
                  "building_subsistence_")  # subsistence: the peasants' economy, owned by manors by default
CLASSES = ["gov", "company", "manor", "findist", "f_pop", "f_comp", "f_gov", "self", "other"]
POP = ("manor", "findist", "f_pop")


# --- variables --------------------------------------------------------------------------------------------------------


def _value(kind: str, ident: str | None, tags: dict[str, str]) -> str:
    if kind == "value":
        n = int(ident or 0)
        if n >= 1 << 63:
            n -= 1 << 64
        return f"{n / DIV:.6g}"
    if kind == "ctry":
        return tags.get(ident or "", f"ctry:{ident}")
    if kind == "boolean":
        return "yes" if ident else "no"
    return f"{kind}:{ident}"


_VAR = re.compile(r"flag=(\w+)\s+(?:tick=\d+\s+)?data=\{\s*type=(\w+)\s*(?:identity=(-?\d+))?")
_MAP = re.compile(r'name="(\w+)"\s*list=\{')
_PAIR = re.compile(r"key=\{\s*type=(\w+)\s*(?:identity=(-?\d+))?\s*\}\s*value=\{\s*type=(\w+)\s*(?:identity=(-?\d+))?")


def variables(b: Block | None, tags: dict[str, str], pattern: str = ".") -> tuple[list, list]:
    """(variables [(name, value)], maps [(name, [(key, value)])]) of a block with ``variables={…}``."""
    if b is None:
        return [], []
    v = b.block("variables")
    if v is None:
        return [], []
    rx = re.compile(pattern)
    text = v.text
    vals = [(m.group(1), _value(m.group(2), m.group(3), tags)) for m in _VAR.finditer(text) if rx.search(m.group(1))]
    maps = []
    for m in _MAP.finditer(text):
        if not rx.search(m.group(1)):
            continue
        depth, i = 0, m.end() - 1
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        body = text[i:j + 1]
        maps.append((m.group(1), [(_value(a, b_, tags), _value(c, d, tags)) for a, b_, c, d in _PAIR.findall(body)]))
    return vals, maps


# --- ownership --------------------------------------------------------------------------------------------------------


@dataclass
class Holdings:
    date: str
    tags: dict[str, str]  # country id → tag
    buildings: dict[str, tuple[str, str]]  # building id → (type, country id); removed buildings left out
    companies: dict[str, str]  # HQ building id → company type
    owned: dict[tuple[str, str, str], int] = field(default_factory=dict)  # (owner kind, owner id, building id) → levels
    extra: dict[str, set[str]] = field(default_factory=dict)  # a class name → company types (globs) put into it
    skip: tuple[str, ...] = ()  # more building-type prefixes that are not production (a mod's own)


def holdings(s: Save, extra: dict[str, list[str]] | None = None, skip: tuple[str, ...] = ()) -> Holdings:
    states = s.states()
    blds = {}
    for bid, b in s.entries("building_manager"):
        st = b.get("state")
        if not st or st == DEAD_STATE:
            continue
        blds[bid] = (b.get("building", "") or "", states.get(st, ("", ""))[0])
    comp = {b.get("building", ""): b.get("company_type", "") or "" for _cid, b in s.entries("companies")}
    h = Holdings(s.date, s.countries(), blds, comp, extra={k: set(v) for k, v in (extra or {}).items()},
                 skip=tuple(skip))
    for _oid, b in s.entries("building_ownership_manager"):
        if b.get("privatization") == "yes":
            continue
        ident = b.block("identity")
        if ident is None:
            continue
        kind, oid = ("country", ident.get("country")) if ident.get("country") else ("building", ident.get("building"))
        owned = b.get("building")
        if oid and owned:
            h.owned[(kind, oid, owned)] = int(number(b.get("levels")))
    return h


def production(btype: str, skip: tuple[str, ...] = ()) -> bool:
    return bool(btype) and btype not in NONPROD and not btype.startswith(NONPROD_PREFIX + skip)


def classify(h: Holdings, kind: str, oid: str, bid: str) -> tuple[str | None, str | None]:
    """(tag of the building's country, owner class) of an ownership record, or (None, None) for non-production."""
    b = h.buildings.get(bid)
    if not b or not production(b[0], h.skip):
        return None, None
    cty = h.tags.get(b[1], b[1])
    if kind == "country":
        return cty, "gov" if h.tags.get(oid) == cty else "f_gov"
    ob = h.buildings.get(oid)
    if not ob:
        return cty, "other"
    ctype = h.companies.get(oid) or (ob[0][len("building_regional_company_"):] if ob[0].startswith(
        "building_regional_company_") else "")
    if ob[0] in OWNER_BUILDINGS:
        cl = OWNER_BUILDINGS[ob[0]]
    elif ctype:
        cl = next((name for name, globs in h.extra.items() if any(fnmatch.fnmatch(ctype, g) for g in globs)),
                  "company")
    elif oid == bid:
        cl = "self"
    else:
        cl = "other"
    if h.tags.get(ob[1], ob[1]) != cty:
        cl = "f_pop" if cl in ("manor", "findist") else "f_comp"
    return cty, cl


def levels_by_class(h: Holdings) -> dict[str, Counter]:
    tot: dict[str, Counter] = defaultdict(Counter)
    for (k, o, b), lv in h.owned.items():
        c, cl = classify(h, k, o, b)
        if c:
            tot[c][cl] += lv
            tot["WORLD"][cl] += lv
    return tot


def additions(a: Holdings, b: Holdings) -> dict[str, Counter]:
    """Gross additions between two saves: per (owner, building) the positive change of levels, by class."""
    add: dict[str, Counter] = defaultdict(Counter)
    for key, lv in b.owned.items():
        d = lv - a.owned.get(key, 0)
        if d > 0:
            c, cl = classify(b, *key)
            if c:
                add[c][cl] += d
                add["WORLD"][cl] += d
    return add


def transfers(a: Holdings, b: Holdings) -> dict[str, Counter]:
    """Levels that changed owner while their building kept its size: lost (−) and gained (+) by class."""
    size_a: Counter = Counter()
    size_b: Counter = Counter()
    for (_k, _o, bid), lv in a.owned.items():
        size_a[bid] += lv
    for (_k, _o, bid), lv in b.owned.items():
        size_b[bid] += lv
    out: dict[str, Counter] = defaultdict(Counter)
    for key in set(a.owned) | set(b.owned):
        bid = key[2]
        if size_a[bid] != size_b[bid] or not size_a[bid]:
            continue
        d = b.owned.get(key, 0) - a.owned.get(key, 0)
        if d:
            c, cl = classify(b if key in b.owned else a, *key)
            if c:
                out[c][cl] += d
                out["WORLD"][cl] += d
    return out


# --- buildings, companies, goods --------------------------------------------------------------------------------------


def buildings_of(s: Save, btype: str) -> dict[str, dict]:
    """Per country tag: buildings of a type — levels, weekly sales / costs / profit, owned levels by owner kind."""
    h = holdings(s)
    owners: dict[str, Counter] = defaultdict(Counter)
    for (kind, oid, bid), lv in h.owned.items():
        if h.buildings.get(bid, ("",))[0] != btype:
            continue
        ob = h.buildings.get(oid, ("", ""))[0] if kind == "building" else ""
        k = ("country" if kind == "country" else OWNER_BUILDINGS.get(ob)
             or ("company" if oid in h.companies or ob.startswith("building_regional_company_") else "other"))
        owners[bid][k] += lv
    out: dict[str, dict] = {}
    for bid, b in s.entries("building_manager"):
        if b.get("building") != btype or b.get("state") in (None, DEAD_STATE):
            continue
        tag = h.tags.get(h.buildings.get(bid, ("", ""))[1], "?")
        row = out.setdefault(tag, {"buildings": 0, "levels": 0, "sales": 0.0, "cost": 0.0, "profit": 0.0,
                                   "owners": Counter()})
        row["buildings"] += 1
        row["levels"] += int(number(b.get("levels")))
        row["sales"] += number(b.get("goods_sales"))
        row["cost"] += number(b.get("goods_cost"))
        row["profit"] += number(b.get("profit_after_reserves"))
        row["owners"].update(owners.get(bid, Counter()))
    return out


def company_holdings(s: Save, pattern: str = "") -> list[dict]:
    """Companies whose type contains ``pattern``: country, HQ, levels by building type."""
    h = holdings(s)
    by_owner: dict[str, Counter] = defaultdict(Counter)
    for (kind, oid, bid), lv in h.owned.items():
        if kind == "building":
            by_owner[oid][h.buildings.get(bid, ("?",))[0]] += lv
    out = []
    for cid, b in s.entries("companies"):
        ctype = b.get("company_type", "") or ""
        if pattern and pattern not in ctype:
            continue
        hq = b.get("building", "") or ""
        regional = [oid for oid, bt in h.buildings.items() if bt[0] == f"building_regional_company_{ctype}"]
        levels: Counter = Counter()
        for oid in [hq, *regional]:
            levels.update(by_owner.get(oid, Counter()))
        out.append({"id": cid, "type": ctype, "country": h.tags.get(b.get("country", ""), b.get("country")),
                    "hq": hq, "levels": dict(levels.most_common())})
    return out


def goods_flows(s: Save, goods_id: str) -> dict[str, dict]:
    """Per country tag: units a week of one goods (the save's numeric id) bought by buildings and made, and the
    building types that buy most."""
    states = s.states()
    tags = s.countries()
    out: dict[str, dict] = {}
    for _bid, b in s.entries("building_manager"):
        st = b.get("state")
        if not st or st == DEAD_STATE:
            continue
        tag = tags.get(states.get(st, ("", ""))[0], "?")
        for side in ("input_goods", "output_goods"):
            g = b.block(side)
            goods = g.block("goods") if g else None
            e = goods.block(goods_id) if goods else None
            if e is None:
                continue
            v = number(e.get("value"))
            row = out.setdefault(tag, {"input": 0.0, "output": 0.0, "buyers": Counter()})
            if side == "input_goods":
                row["input"] += v
                if v:
                    row["buyers"][b.get("building", "?")] += v
            else:
                row["output"] += v
    return out


def goods_ids(s: Save, btype: str) -> list[str]:
    """The output goods ids of the first building of a type (to find a goods' numeric id)."""
    for _bid, b in s.entries("building_manager"):
        if b.get("building") == btype:
            g = b.block("output_goods")
            goods = g.block("goods") if g else None
            return [k for k, _v in goods.items()] if goods else []
    return []
