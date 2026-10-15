import json

import pytest
from conftest import write

from vic3tools import cli, hook_lint
from vic3tools.core import vfs
from vic3tools.core.vfs import Mod
from vic3tools.index import query
from vic3tools.lint import rules, run, tiger


@pytest.fixture
def lset(tmp_path, home):
    van, m1 = tmp_path / "van" / "game", tmp_path / "m1"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "gui/a_panel.gui", "types T {\n\ttype my_panel = window {\n\t\tsize = { 10 10 }\n\t}\n}\n")
    write(m1 / "gui/my_panel.gui", "types M {\n\ttype my_panel = window {\n\t\tsize = { 20 20 }\n\t}\n"
                                   "\ttype own_panel = window {}\n}\n")
    write(m1 / "gui/broken.gui", "window = {\n\ttextbox = {\n\t\ttext = \"X\"\n\t}\n")
    write(m1 / "common/scripted_effects/e.txt", "my_effect = {\n\tdebug_log = \"Привет\"\n}\n")
    write(m1 / "localization/english/m_l_english.yml", 'l_english:\n X: "x"\n')
    write(m1 / "v3-lint.toml", '[[rule]]\nname = "no-debug"\nfiles = "common/**"\npattern = "debug_log"\n'
                               'message = "debug output left in"\n\n'
                               '[[suppress]]\nkey = "bom"\nfile = "localization/*"\nwhy = "tested"\n')
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    si = query.SetIndex.open(vfs.ModSet.from_dirs([m1]))
    yield si
    si.close()


def test_file_rules(lset):
    mod = lset.ms.mods[1]
    project, sup = rules.project_rules(mod)
    assert [r.key for r in rules.file_rules(mod, "gui/broken.gui", project)] == ["braces"]
    assert rules.file_rules(mod, "gui/broken.gui", project)[0].line == 1
    assert [r.key for r in rules.file_rules(mod, "common/scripted_effects/e.txt", project)] == ["bom", "rule:no-debug"]
    loc = rules.file_rules(mod, "localization/english/m_l_english.yml", project)
    assert [r.key for r in loc] == ["bom"]
    assert sup[0]["why"] == "tested"


def test_gui_type_ignored(lset):
    found = rules.gui_types_ignored(lset, 1)
    # vanilla's a_panel.gui sorts before the mod's my_panel.gui: the mod's my_panel never applies
    assert [(r.path, r.line) for r in found] == [("gui/my_panel.gui", 2)]
    assert "vanilla gui/a_panel.gui:2" in found[0].message


def test_baseline_and_suppress(lset):
    mod = lset.ms.mods[1]
    reports, _notes = run.collect(lset, 1, use_tiger=False, only=("braces", "bom", "gui-type-ignored"))
    res = run.split(mod, reports)
    assert {r.key for r in res.shown} == {"braces", "bom", "gui-type-ignored", "rule:no-debug"}
    assert [r.path for r, _why in res.suppressed] == ["localization/english/m_l_english.yml"]
    run.write_baseline(mod, res.shown)
    again = run.split(mod, reports)
    assert again.shown == [] and len(again.baselined) == len(res.shown)
    # a new report with the same fingerprint beyond the count shows again
    again = run.split(mod, reports + [res.shown[0]])
    assert again.shown == [res.shown[0]]


def test_flaky_scope_reports_match_both_ways(tmp_path):
    mod = Mod("m", tmp_path)
    a = tiger.Report("warning", "", "scopes", "`prev` produces company but expected country", "f.txt", 1, 0, "x = prev")
    b = tiger.Report("warning", "", "scopes", "`prev` produces country but expected company", "f.txt", 9, 0, "x = prev")
    run.write_baseline(mod, [a])
    assert run.split(mod, [b, b, b]).shown == []  # the other deduction, any count


def test_cli_lint_no_tiger(lset, capsys):
    m1 = str(lset.ms.mods[1].path)
    rc = cli.main(["--lang", "en", "lint", "--no-tiger", "--mods", m1])
    out = capsys.readouterr().out
    assert rc == 1  # errors shown
    assert "gui/broken.gui" in out and "braces" in out and "suppressed 1" in out
    rc = cli.main(["--lang", "en", "lint", "--no-tiger", "--mods", m1, "--file", "gui/my_panel.gui", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert [r["key"] for r in data["reports"]] == ["gui-type-ignored"] and rc == 0


def test_hook_after_edit(lset):
    ms = lset.ms
    f = ms.mods[1].path / "gui/broken.gui"
    out = hook_lint.check({"tool_name": "Edit", "tool_input": {"file_path": str(f), "new_string": "text = \"X\""}},
                          ms)
    assert "gui/broken.gui:1" in out and "braces" in out
    assert hook_lint.check({"tool_input": {"file_path": str(ms.mods[0].path / "gui/a_panel.gui")}}, ms) == ""
    assert hook_lint.run("not json") == ""


def test_tiger_parse_and_config(tmp_path):
    raw = json.dumps([
        {"severity": "error", "confidence": "strong", "key": "missing-item", "message": "x not defined",
         "locations": [{"from": "MOD", "path": "common\\a.txt", "linenr": 3, "column": 2, "line": "\tx = y"},
                       {"from": "MOD", "path": "common\\b.txt", "linenr": 9}]},
        {"severity": "warning", "key": "scopes", "message": "in a dependency",
         "locations": [{"from": "CMF", "path": "common\\c.txt", "linenr": 1}]},
    ])
    rs = tiger.parse(raw)
    assert [(r.key, r.where, r.text, r.also) for r in rs] == [("missing-item", "common/a.txt:3", "x = y",
                                                               ("common/b.txt:9",))]
    mod = Mod("mine", tmp_path / "mine")
    write(mod.path / "vic3-tiger.conf", 'load_mod = {\n\tmod = "' + (tmp_path / "dep1").as_posix() + '"\n}\n')
    conf = tiger.config_text(mod, [Mod("dep1", tmp_path / "dep1"), Mod("[1.13] Dep 2", tmp_path / "dep2")])
    assert conf.count("load_mod") == 2 and 'label = "1.13 Dep 2"' in conf
