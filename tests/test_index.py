import pytest
from conftest import write

from vic3tools import cli
from vic3tools.core import vfs
from vic3tools.index import db, query


@pytest.fixture
def setidx(tmp_path, home):
    van, m1 = tmp_path / "van" / "game", tmp_path / "m1"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "common/scripted_effects/e.txt",
          "my_effect = {\n\tset_variable = { name = my_var value = 1 }\n}\n"
          "caller = {\n\tif = { limit = { always = yes }\n\t\tmy_effect = yes\n\t}\n}\n")
    write(van / "common/script_values/v.txt", "my_value = {\n\tvalue = var:my_var\n}\n# my_effect in a comment\n")
    write(van / "localization/english/a_l_english.yml",
          'l_english:\n LAW_GIVES: "Law [Law.GetName] gives $WHAT$ at level [L|v]"\n')
    write(van / "localization/russian/a_l_russian.yml",
          'l_russian:\n LAW_GIVES: "Закон [Law.GetName] даёт $WHAT$ на уровне [L|v]"\n')
    write(van / "gui/p.gui", 'types T {\n\ttype my_panel = window {\n\t\tname = "the_panel"\n'
                             '\t\ttextbox = {\n\t\t\ttext = "MY_TEXT"\n\t\t\tsize = { 10 20 }\n\t\t}\n\t}\n}\n'
                             "template my_tpl {\n\tfontsize = 20\n}\n")
    write(m1 / "common/scripted_effects/m.txt", "user = { my_effect = yes }\n")
    write(m1 / "_archive/common/scripted_effects/old.txt", "old = { set_variable = { name = my_var } }\n")
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    si = query.SetIndex.open(vfs.ModSet.from_dirs([m1]))
    yield si
    si.close()


def test_defs_with_ranges(setidx):
    d = setidx.defs("my_effect")
    assert [(h.kind, h.folder, h.line, h.end_line) for h in d] == [("db", "common/scripted_effects", 1, 3)]
    assert [(h.kind, h.line, h.end_line) for h in setidx.defs("my_panel")] == [("gui_type", 2, 8)]
    assert setidx.defs("my_tpl")[0].kind == "gui_template"
    assert {h.folder for h in setidx.defs("LAW_GIVES")} == {"english", "russian"}


def test_refs_ctx_path_writes_and_loads(setidx):
    r = setidx.refs("my_effect")
    assert [(h.mod.name, h.ctx, h.path) for h in r] == [("vanilla", "caller", "if>my_effect"),
                                                        ("m1", "user", "user>my_effect")]
    v = setidx.refs("my_var")
    assert sorted((h.ctx, h.writes, h.loads) for h in v) == [("my_effect", True, True), ("my_value", False, True),
                                                             ("old", True, False)]
    assert setidx.refs("WHAT")[0].path == "loc"  # $WHAT$ in a loc string
    assert setidx.names_like("my_v*") == ["my_value", "my_var"]
    assert [h.rel for h in setidx.scan_refs("always")] == ["common/scripted_effects/e.txt"]


def test_loc_text_search(setidx):
    found = setidx.loc_search("Закон Образование даёт школы на уровне 2")
    assert found and found[0][1].name == "LAW_GIVES" and found[0][1].folder == "russian"
    assert setidx.loc_search("nothing like it") == []


def test_outline(setidx):
    nodes = query.outline(setidx.ms.mods[0].path / "gui/p.gui")
    rows = [(lv, n.key, n.label, n.line, n.end_line) for lv, n in query.flatten(nodes, 4)]
    assert rows[:3] == [(0, "types T", "", 1, 9), (1, "type my_panel window", "the_panel", 2, 8),
                        (2, "textbox", "text: MY_TEXT", 4, 7)]
    assert all(n.key != "size" for _, n in query.flatten(nodes, 4))  # one-line property blocks are left out
    assert [n.key for _, n in query.find_nodes(nodes, "my_text")] == ["textbox"]


def test_refresh_drops_and_rereads(setidx, tmp_path):
    m1 = setidx.ms.mods[1]
    (m1.path / "common/scripted_effects/m.txt").write_text("user2 = { my_effect = yes }\n", encoding="utf-8")
    con = db.open_index(m1)
    ctx = con.execute("SELECT c.name FROM refs r JOIN names c ON c.id = r.ctx_id").fetchall()
    con.close()
    assert ("user2",) in ctx and ("user",) not in ctx


def test_cli_def_refs_loc_outline(setidx, capsys):
    m1 = str(setidx.ms.mods[1].path)
    assert cli.main(["--lang", "en", "def", "my_effect", "--mods", m1]) == 0
    assert "e.txt:1-3" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "refs", "my_var", "--mods", m1]) == 0
    out = capsys.readouterr().out
    assert "2 reference(s), 1 of them writes" in out and "never loads" in out
    assert cli.main(["--lang", "en", "loc", "LAW_GIVES", "--mods", m1]) == 0
    assert "Закон" in capsys.readouterr().out
    assert cli.main(["outline", str(setidx.ms.mods[0].path / "gui/p.gui"), "--at", "5"]) == 0
    assert "textbox" in capsys.readouterr().out
