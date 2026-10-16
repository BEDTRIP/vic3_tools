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


def test_triage_groups_and_verdicts(tmp_path):
    mod = Mod("m", tmp_path)

    def rep(msg, path="common/x.txt", key="missing-item"):
        return tiger.Report("error", "", key, msg, path, 1, 0, msg)

    reports = [rep("building type `building_company_A` not defined in common/buildings/"),
               rep("building type `building_company_B` not defined in common/buildings/"),
               rep("script value `x_valid` not defined in common/script_values/", "localization/english/a.yml"),
               rep("required field `limit` missing", key="field-missing"),
               rep("unknown align Hcenter", "gui/p.gui", "choice")]
    (tmp_path / "v3-lint.toml").write_text(
        '[[suppress]]\nkey = "missing-item"\nmessage = "building_company_"\nwhy = "engine-made HQs"\n'
        '[[suppress]]\nkey = "missing-item"\nfile = "localization/*"\nplan = "R12 L.1"\n', encoding="utf-8")
    run.write_baseline(mod, [reports[3]])
    groups = run.triage(run.split(mod, reports))
    got = [(g.verdict, g.key, g.template, g.count) for g in groups]
    assert got == [("new", "choice", "unknown align Hcenter", 1),
                   ("untriaged", "field-missing", "required field X missing", 1),
                   ("tracked", "missing-item", "script value X not defined in X/", 1),
                   ("noise", "missing-item", "building type X not defined in X/", 2)]
    assert dict(groups[-1].names) == {"building_company_A": 1, "building_company_B": 1}
    assert list(groups[2].reasons) == ["R12 L.1"]


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


def test_tiger_load_order_noise(tmp_path, home):
    van, m1, m2 = tmp_path / "van" / "game", tmp_path / "m1", tmp_path / "m2"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "common/production_methods/14_companies.txt", "pm_hq = {\n}\n")
    write(van / "common/ideologies/00_ig.txt", "ideology_a = {\n}\n")
    write(m1 / "common/ideologies/zz_dep.txt", "ideology_dep = {\n}\n")
    write(m2 / "common/production_methods/11_mine.txt", "REPLACE:pm_hq = {\n}\nREPLACE:pm_none = {\n}\n"
                                                         "REPLACE:ideology_a = {\n}\n")
    write(m2 / "common/ideologies/00_ef.txt", "INJECT:ideology_a = {\n}\nINJECT:ideology_dep = {\n}\n")
    write(m2 / "v3-lint.toml", '[[suppress]]\nkey = "prefixes"\nplan = "broad rule"\n')
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")

    def rep(path, line, text, msg="replacing a non-existing item"):
        return tiger.Report("error", "strong", "prefixes", msg, path, line, 0, text)

    pm, ide = "common/production_methods/11_mine.txt", "common/ideologies/00_ef.txt"
    reports = [rep(pm, 1, "REPLACE:pm_hq = {"), rep(pm, 3, "REPLACE:pm_none = {"),
               rep(pm, 5, "REPLACE:ideology_a = {"),  # defined, but in another folder: a real error
               rep(ide, 1, "INJECT:ideology_a = {", "injecting into a non-existing item"),
               rep(ide, 3, "INJECT:ideology_dep = {", "injecting into a non-existing item"),
               rep("common/game_rules/r.txt", 1, "TRY_REPLACE:rule_x = {", "cannot use prefixes with game rule")]
    si = query.SetIndex.open(vfs.ModSet.from_dirs([m1, m2]))
    try:
        run.tiger_order_noise(si, 2, reports)
    finally:
        si.close()
    assert [bool(r.noise) for r in reports] == [True, False, False, True, True, False]
    assert "vanilla common/production_methods/14_companies.txt" in reports[0].noise
    assert "m1 common/ideologies/zz_dep.txt" in reports[4].noise
    # noise wins over the mod's own rules: it is told apart from what the mod tracks
    res = run.split(Mod("m2", m2), reports)
    assert res.shown == [] and len(res.suppressed) == 6
    groups = {g.template: dict(g.status) for g in run.triage(res)}
    assert groups == {"replacing a non-existing item": {"tracked": 2, "noise": 1},
                      "cannot use prefixes with game rule": {"tracked": 1},
                      "injecting into a non-existing item": {"noise": 2}}
