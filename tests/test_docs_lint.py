"""v3 docs check: a node with one member repo, built in a temporary folder."""

from pathlib import Path

from conftest import write

from vic3tools import docs_lint

HEAD = '---\ntype: {type}\ndescription: "d"\nproject: p\ntags: [t]\n{extra}---\n'


def doc(path: Path, type_: str = "how-to", body: str = "# x\n", extra: str = "") -> Path:
    return write(path, HEAD.format(type=type_, extra=extra) + body)


def vault(tmp_path: Path) -> Path:
    node, mod = tmp_path / "node", tmp_path / "node" / "mod"
    write(node / "docs-check.toml", 'project = "p"\nmembers = ["mod"]\ndocs = ["docs/**"]\ncomponents = ["MOD"]\n')
    write(mod / "docs-check.toml", 'name = "mod"\nproject = "p"\nnode = "p"\ndocs = ["docs/**"]\n'
                                   'code_ext = [".txt"]\ncover = ["common/**"]\ncode_roots = ["common/"]\n')
    doc(node / "docs" / "план" / "Этап 1. Начало.md", "epic", "# Этап 1\n\nрешение [[ADR-0001 — да]]\n",
        "status: in-progress\ndate: 2026-10-29\n")
    doc(node / "docs" / "план" / "задачи" / "MOD-1 — сделать.md", "issue", "# MOD-1\n",
        'kind: task\ncomponent: MOD\nepic: "[[Этап 1. Начало]]"\ndate: 2026-10-29\nstatus: todo\n'
        'touches: ["mod/common/", "сервер"]\n')
    doc(mod / "docs" / "решения" / "ADR-0001 — да.md", "adr", "# Да?\n",
        "status: accepted\ndate: 2026-10-29\ndeciders: человек\n")
    doc(mod / "docs" / "код" / "a.md", "code", "# A\n\nСм. `common/a.txt`.\n", 'paths: ["common/a.txt"]\n')
    write(mod / "common" / "a.txt", "# ADR-0001, MOD-1\nx = 1\n")
    return node


def codes(res) -> list[tuple[str, str]]:
    return sorted((f.file, f.code) for f in res.failures)


def test_clean_vault(tmp_path):
    node = vault(tmp_path)
    res = docs_lint.check(node)
    assert codes(res) == []
    assert res.checked == {"node": 2, "mod": 2}


def test_findings(tmp_path):
    node = vault(tmp_path)
    mod = node / "mod"
    write(mod / "docs" / "bare.md", "# no header\n")
    doc(mod / "docs" / "links.md", body="[[Нет такого]] [[a#Нет раздела]] [x](a.md)\n")
    doc(mod / "docs" / "код" / "b.md", "code", "# B\n", 'paths: ["common/none.txt"]\n')
    write(mod / "common" / "b.txt", "# ADR-0009 MOD-9\n")  # no document's paths, an unknown ADR and issue
    write(mod / "docs" / "история" / "old.md", "no header, ADR-0001 as text — history keeps it\n[[Нет]]\n")
    res = docs_lint.check(mod)  # from the member: its documents, links over the whole vault
    assert ("common/b.txt", "uncovered") in [(f.file, f.code) for f in res.findings if f.note]  # not cover_strict
    assert codes(res) == [
        ("common/b.txt", "code_decision"), ("common/b.txt", "code_task"),
        ("docs/bare.md", "no_header"),
        ("docs/links.md", "anchor"), ("docs/links.md", "link_nowhere"), ("docs/links.md", "md_link"),
        ("docs/история/old.md", "link_nowhere"),
        ("docs/код/b.md", "paths_missing"),
    ]


def test_mentions_fix(tmp_path):
    node = vault(tmp_path)
    p = doc(node / "mod" / "docs" / "код" / "c.md", "code",
            "# C\n\nПо ADR-0001, этап 1, MOD-1; в таблице:\n\n| a |\n| --- |\n| ADR-0001 |\n",
            'paths: ["common/a.txt"]\n')
    res = docs_lint.check(node)
    assert [f.arg.split("@")[0] for f in res.failures if f.code == "mention"] == \
        ["ADR-0001", "этап 1", "MOD-1", "ADR-0001"]
    docs_lint.check(node, fix=True)
    assert p.read_text(encoding="utf-8").endswith(
        "По [[ADR-0001 — да|ADR-0001]], [[Этап 1. Начало|этап 1]], [[MOD-1 — сделать|MOD-1]]; в таблице:\n\n"
        "| a |\n| --- |\n| [[ADR-0001 — да\\|ADR-0001]] |\n")
    assert codes(docs_lint.check(node)) == []


def test_ambiguous_and_known(tmp_path):
    node = vault(tmp_path)
    doc(node / "docs" / "README.md")
    doc(node / "mod" / "docs" / "README.md")
    doc(node / "mod" / "docs" / "e.md", body="[[README]]\n")
    res = docs_lint.check(node)
    assert codes(res) == [("docs/e.md", "link_ambiguous")]
    # the known list is not code, though it is a .txt and names ADR
    write(node / "mod" / "docs-check-known.txt", "docs/e.md: link_ambiguous README  # why, not ADR-0009\n")
    res = docs_lint.check(node)
    assert codes(res) == [] and res.known == 1


def test_standalone_repo(tmp_path):
    node = vault(tmp_path)
    mod = node / "mod"
    (node / "docs-check.toml").unlink()  # the repo's CI: no node around it
    write(mod / "common" / "a.txt", "x = 1\n")  # issue keys live in the node
    doc(mod / "docs" / "f.md", body="[[Этап 1. Начало]]\n")
    res = docs_lint.check(mod)
    assert codes(res) == []
    assert {f.code for f in res.findings if f.note} == {"link_outside", "orphan"}


def test_globs():
    assert docs_lint.matches("common/x/y.txt", ["common/**"])
    assert docs_lint.matches("common/x/y.txt", ["common/x"])
    assert docs_lint.matches("common/history/a/b.txt", ["common/history/*"])
    assert not docs_lint.matches("gui/a.gui", ["common/**"])
    assert docs_lint.matches("README.md", ["**/*.md"])


def test_agent_notes(tmp_path):
    """audience: agent — only a mark for a person's filter: no orphan, links into it from any text are fine."""
    node = vault(tmp_path)
    mod = node / "mod"
    doc(mod / "docs" / "агенту" / "Выписка.md", "reference", extra="audience: agent\n")  # nobody links: no orphan
    doc(mod / "docs" / "агенту" / "Разбор.md", "reference", "# R\n\n[[Выписка]]\n", "audience: agent\n")
    doc(mod / "docs" / "код" / "c.md", "code", "# C\n\n[[Разбор]]\n", 'paths: ["common/a.txt"]\n')
    doc(mod / "docs" / "код" / "d.md", "code", "# D\n", 'paths: ["common/a.txt"]\nuses: ["[[Разбор]]"]\n')  # header: ok
    write(mod / "docs" / "история" / "old.md", "[[Разбор]]\n")
    res = docs_lint.check(node)
    assert codes(res) == []
    notes = [(f.file, f.code) for f in res.findings if f.note]
    assert not any(c == "link_to_agent" for _, c in notes)
    assert not any(c == "orphan" and "агенту" in f for f, c in notes)


def test_issues_and_tables(tmp_path):
    node = vault(tmp_path)
    t = node / "docs" / "план" / "задачи"
    doc(t / "MOD-2 — взята.md", "issue", "# x\n", 'kind: task\ncomponent: MOD\nepic: "[[Этап 1. Начало]]"\n'
        'date: 2026-11-20\nstatus: in-progress\ntouches: ["mod/nowhere/"]\ndepends: ["[[Этап 1. Начало]]"]\n')
    doc(t / "MOD-3 — закрыта.md", "issue", "# x\n", 'kind: task\ncomponent: MOD\nepic: "[[Этап 1. Начало]]"\n'
        'date: 2026-11-20\nstatus: done\nverified_by: глазами\n')
    doc(t / "XX-1 — чужая.md", "issue", "# x\n", 'kind: bug\ncomponent: XX\nepic: "[[Этап 1. Начало]]"\n'
        'date: 2026-11-20\nstatus: fixed\n')
    doc(node / "docs" / "решения" / "Про что.md", "adr",
        "# x\n\n| a | b |\n| --- | --- |\n| [[ADR-0001 — да|да]] | 2 |\n", "status: superseded\ndate: 2026-11-20\n")
    res = docs_lint.check(node)
    got = sorted((f.file.rsplit("/", 1)[-1], f.code, f.arg.split("@")[0]) for f in res.failures)
    assert got == [
        ("MOD-2 — взята.md", "depends_type", "[[Этап 1. Начало]]"),
        ("MOD-2 — взята.md", "need", "assignee"), ("MOD-2 — взята.md", "need", "claimed"),
        ("MOD-2 — взята.md", "touches_missing", "mod/nowhere/"),
        ("MOD-3 — закрыта.md", "issue_closed_place", "done"),
        ("XX-1 — чужая.md", "component", "XX"),
        ("XX-1 — чужая.md", "need", "fixed_in"), ("XX-1 — чужая.md", "severity", ""),
        ("Про что.md", "adr_name", ""), ("Про что.md", "need", "superseded_by"),
        ("Про что.md", "table_cells", ""),
    ]
