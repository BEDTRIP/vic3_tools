"""v3 graph on a tiny snapshot: cards, links, backlinks, hand sections, terms."""

from __future__ import annotations

from pathlib import Path

from vic3tools import graph
from vic3tools.graph import run


def _w(p: Path, text: str, bom: bool = True) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def _setup(tmp_path: Path) -> graph.Config:
    van = tmp_path / "out" / "van"
    _w(van / "common/buildings/b.txt", "building_bakery = {\n\tproduction_method_groups = { pmg_bread }\n"
       "\tunlocking_technologies = { baking }\n\tis_visible = { always = yes }\n}\n")
    _w(van / "common/production_method_groups/g.txt", "pmg_bread = { production_methods = { pm_bread } }\n")
    _w(van / "common/production_methods/p.txt", "pm_bread = {\n\tbuilding_modifiers = { workforce_scaled = {\n"
       "\t\tgoods_input_grain_add = 10\n\t\tgoods_output_bread_add = 20\n\t} }\n}\n")
    _w(van / "common/goods/g.txt", "grain = { cost = 20 }\nbread = { cost = 30 }\n")
    _w(van / "common/technology/technologies/t.txt", "baking = { era = era_1 }\n")
    _w(van / "common/game_concepts/c.txt", "concept_bread = { texture = x }\n")
    _w(van / "localization/russian/a_l_russian.yml", 'l_russian:\n building_bakery:0 "Пекарня"\n grain:0 "Зерно"\n'
       ' bread:0 "Хлеб"\n concept_bread:0 "Хлеб"\n concept_bread_desc:0 "Еда из [grain|l]."\n')
    _w(van / "localization/english/a_l_english.yml", 'l_english:\n building_bakery:0 "Bakery"\n')
    docs = tmp_path / "out" / "docs"
    _w(docs / "graph.toml", 'version = "1.13"\npaths_root = ".."\n[sources.vanilla]\nsnapshot = "../van"\n'
       'label = "ваниль"\n', bom=False)
    return graph.load(docs)


def test_objects_cards_and_links(tmp_path):
    cfg = _setup(tmp_path)
    run.run_terms(cfg, False)
    s, n = run.run_objects(cfg, False)
    assert n["cards"] == 6 and not s.stale
    v = cfg.root / "vanilla"
    bakery = (v / "Здания/Пекарня.md").read_text(encoding="utf-8")
    assert "paths: [van/common/buildings/b.txt]" in bakery
    assert "[[vanilla/Технологии/baking|baking]]" in bakery
    assert "- **is_visible**: скрипт, строки 4–4" in bakery
    pm = (v / "Методы производства/pm_bread.md").read_text(encoding="utf-8")
    assert "`goods_input_grain_add` = `10` → [[vanilla/Товары/Зерно|Зерно]]" in pm
    # the good's name is a term's name too: the card gets its type
    bread = (v / "Товары/Хлеб (товар).md").read_text(encoding="utf-8")
    assert "- **Методы производства** (выход): [[vanilla/Методы производства/pm_bread|pm_bread]]" in bread
    tech = (v / "Технологии/baking.md").read_text(encoding="utf-8")
    assert "(открывает): [[vanilla/Здания/Пекарня|Пекарня]]" in tech


def test_hand_section_kept_and_check(tmp_path):
    cfg = _setup(tmp_path)
    run.run_objects(cfg, False)
    card = cfg.root / "vanilla/Здания/Пекарня.md"
    card.write_text(card.read_text(encoding="utf-8") + "\n## Зачем в механике\n\nруками\n", encoding="utf-8")
    s, _ = run.run_objects(cfg, True)
    assert s.changed == ["Здания/Пекарня.md"]  # the hand section is appended after the generated text
    run.run_objects(cfg, False)
    assert card.read_text(encoding="utf-8").endswith("## Зачем в механике\n\nруками\n")
    s, _ = run.run_objects(cfg, True)
    assert not s.changed and not s.stale


def test_mod_layer(tmp_path):
    cfg = _setup(tmp_path)
    mod = tmp_path / "out" / "mod"
    _w(mod / "common/buildings/zz_mod.txt", "REPLACE:building_bakery = {\n\tproduction_method_groups = { pmg_bread }\n"
       "\tlevels_per_mesh = 5\n}\nbuilding_mill = { production_method_groups = { pmg_bread } }\n")
    _w(mod / "common/scripted_effects/x.txt", "my_effect = { }\n")
    _w(mod / "common/on_actions/x.txt", "on_monthly_pulse = { on_actions = { my_hook } }\n")
    _w(mod / "common/game_concepts/c.txt", "concept_loaf = { }\n")
    _w(mod / "localization/russian/m_l_russian.yml", 'l_russian:\n concept_loaf:0 "Буханка"\n'
       ' concept_loaf_desc:0 "Форма [concept_bread|l]."\n')
    _w(cfg.root / "graph.toml", (cfg.root / "graph.toml").read_text(encoding="utf-8")
       + '[sources.mod]\nsnapshot = "../mod"\nlabel = "Мод"\n', bom=False)
    cfg = graph.load(cfg.root)
    run.run_objects(cfg, False)
    (name, s, n), = run.run_mods(cfg, False)
    assert name == "mod" and n["cards"] == 2
    d = cfg.root / "mod"
    bakery = (d / "Здания/Пекарня.md").read_text(encoding="utf-8")
    assert 'replaces: "[[vanilla/Здания/Пекарня]]"' in bakery
    assert "- **levels_per_mesh**: добавлено" in bakery and "- **unlocking_technologies**: убрано" in bakery
    ref = (d / "Что меняет в ванили — Мод.md").read_text(encoding="utf-8")
    assert "| `buildings` | 1 | 1 | 0 | 0 | 0 | 0 | 0 |" in ref
    assert "- **добавляет** (1): [[mod/Здания/building_mill|building_mill]]" in ref
    assert n["terms"] == 1
    loaf = (d / "Термины/Буханка.md").read_text(encoding="utf-8")
    assert "Форма [[vanilla/Термины/Хлеб|хлеб]]." in loaf and "source: mod" in loaf


def test_audience_in_every_header(tmp_path):
    cfg = _setup(tmp_path)
    toml = cfg.root / "graph.toml"
    text = toml.read_text(encoding="utf-8").replace('paths_root = ".."', 'paths_root = ".."\naudience = "agent"')
    toml.write_text(text, encoding="utf-8")
    cfg = graph.load(cfg.root)
    run.run_terms(cfg, False)
    run.run_objects(cfg, False)
    for f in (cfg.root / "vanilla").rglob("*.md"):
        head = f.read_text(encoding="utf-8").split("\n---\n", 1)[0]
        assert "\nproject: vic3\naudience: agent\n" in head, f


def test_source_own_version(tmp_path):
    cfg = _setup(tmp_path)
    _w(tmp_path / "out" / "mod" / "common/buildings/zz_mod.txt", "building_mill = { }\n")
    _w(cfg.root / "graph.toml", (cfg.root / "graph.toml").read_text(encoding="utf-8").replace("1.13", "1.15")
       + '[sources.mod]\nsnapshot = "../mod"\nlabel = "Мод"\nversion = "1.13"\n', bom=False)
    cfg = graph.load(cfg.root)
    assert cfg.sources["mod"].version == "1.13" and cfg.vanilla.version == ""
    run.run_mods(cfg, False)
    ref = (cfg.root / "mod" / "Что меняет в ванили — Мод.md").read_text(encoding="utf-8")
    assert "меняет в ванили 1.15 (снимок мода — 1.13)" in ref and "сравнение с ваниль 1.15." in ref
    mill = (cfg.root / "mod" / "Здания/building_mill.md").read_text(encoding="utf-8")
    assert "Мод 1.13" in mill
