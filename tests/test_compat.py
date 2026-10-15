import json
import sqlite3

import pytest
from conftest import write

from vic3tools import cli
from vic3tools.compat import audits, conflicts, index, winner
from vic3tools.core import vfs


@pytest.fixture
def mods(tmp_path, home):
    """Vanilla and two mods with the cases the load-order rules are about."""
    van, m1, m2 = tmp_path / "van" / "game", tmp_path / "m1", tmp_path / "m2"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "checksum_manifest.txt", "")
    write(van / "common/buildings/00_b.txt", "b1 = { a = 1 c = 2 }\nb2 = { a = 1 }\n")
    write(van / "common/scripted_effects/e.txt", "eff = { x = 1 }\n")
    write(van / "localization/english/v_l_english.yml", 'l_english:\n K: "vanilla"\n L: "l"\n')
    write(van / "gui/a.gui", "types T {\n\ttype panel = window {\n\t}\n}\n")
    write(m1 / "common/buildings/m1.txt", "INJECT:b1 = { d = 4 }\nREPLACE:b2 = { z = 1 }\n")
    write(m1 / "common/scripted_effects/m1.txt", "eff = { y = 2 }\n")
    write(m1 / "localization/english/m1_l_english.yml", 'l_english:\n K: "mod1"\n')
    write(m1 / "gui/sub/a.gui", "type panel = window {}\n")
    write(m1 / "gui/0.gui", "type early = window {}\n")
    write(m1 / "events/e.txt", "namespace = ev\nev.1 = { }\n")
    write(m2 / "common/buildings/zz.txt", "b1 = { a = 9 }\n")
    write(m2 / "common/buildings/00_b.txt", "b3 = { }\n")  # replaces vanilla's file by path
    write(m2 / "localization/english/replace/r_l_english.yml", 'l_english:\n L: "replaced"\n')
    write(m2 / "events/e2.txt", "ev.1 = { }\n")
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    ms = vfs.ModSet.from_dirs([m1, m2])
    return ms, [index.build(m) for m in ms.mods]


def test_record_chain(mods):
    ms, idx = mods
    v = winner.record(ms, idx, "common/buildings", "b1")
    assert v.winner.file.mod.name == "m2" and v.winner.directive == ""
    notes = [d.note for d in v.defs]
    assert notes[0].startswith("file replaced")  # vanilla's 00_b.txt never loads
    assert notes[1].startswith("nothing to inject")  # so m1's INJECT has no record to go into
    assert winner.record(ms, idx, "common/buildings", "b2").winner is None


def test_first_wins_categories(mods):
    ms, idx = mods
    v = winner.record(ms, idx, "common/scripted_effects", "eff")
    assert v.winner.file.mod.name == "vanilla"
    assert v.defs[1].note.startswith("ignored")


def test_loc_and_gui(mods):
    ms, idx = mods
    k = winner.loc_key(ms, idx, "K")
    assert k.winner.file.mod.name == "vanilla" and "never shows" in k.defs[1].note
    assert winner.loc_key(ms, idx, "L").winner.file.mod.name == "m2"
    g = winner.gui_type(ms, idx, "panel")
    assert g.winner.file.rel == "gui/a.gui" and g.defs[1].note.startswith("ignored")


def test_conflicts_and_audits(mods):
    ms, idx = mods
    o = conflicts.overlap(conflicts.side([idx[1]]), conflicts.side([idx[2]]))
    assert o.keys == ["common/buildings|b1", "events|ev.1"]  # event ids are keys; `namespace` is not
    dead = audits.loc_dead(ms, idx, 1, ("english",))
    assert [(x.key, x.against.split()[0]) for x in dead] == [("K", "vanilla")]
    v2 = vfs.ModSet(ms.mods[:2])  # without m2, vanilla's b2 stays and m1 REPLACEs it
    i2 = idx[:2]
    rep = audits.replace(v2, i2, 1, {})
    assert [(x.key, x.detail) for x in rep] == [("b2", ["a"])]
    dec = audits.replace(v2, i2, 1, {("common/buildings", "b2"): (["a"], "on purpose")})
    assert dec[0].declared == "on purpose"
    assert [(x.key, x.detail) for x in audits.stale(v2, i2, 1, {})] == [("b2", ["a"]), ("eff", ["x"])]


def test_set_file_and_playset(tmp_path, mods, monkeypatch):
    ms, _ = mods
    sf = write(tmp_path / "set.json", json.dumps({"load_order": ["van/game", "m1"], "labels": {"m1": "First"}}))
    s = vfs.ModSet.from_set_file(sf)
    assert [m.kind for m in s.mods] == ["vanilla", "mod"] and s.mods[1].name == "First"
    db = tmp_path / "launcher-v2.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE playsets (id TEXT, name TEXT, isActive INT, isRemoved INT);
        CREATE TABLE mods (id TEXT, displayName TEXT, dirPath TEXT, steamId TEXT);
        CREATE TABLE playsets_mods (playsetId TEXT, modId TEXT, enabled INT, position INT);
        INSERT INTO playsets VALUES ('p', 'Mine', 1, 0);
    """)
    con.executemany("INSERT INTO mods VALUES (?, ?, ?, ?)", [("a", "A", str(tmp_path / "m2"), "1"),
                                                            ("b", "B", str(tmp_path / "m1"), None)])
    con.executemany("INSERT INTO playsets_mods VALUES ('p', ?, ?, ?)", [("a", 1, 1), ("b", 1, 0)])
    con.commit()
    con.close()
    assert [m[0] for m in vfs.playset_mods(db, None)[1]] == ["B", "A"]
    assert vfs.list_playsets(db) == [("Mine", True)]


def test_cli_winner_json(mods, capsys):
    ms, _ = mods
    m1, m2 = ms.mods[1].path, ms.mods[2].path
    assert cli.main(["winner", "--mods", str(m1), str(m2), "--json", "common/buildings", "b1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["winner"]["mod"] == "m2"
    assert cli.main(["audit", "loc-dead", "nope", "--mods", str(m1)]) == 2
