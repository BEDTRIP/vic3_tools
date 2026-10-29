"""v3 docs check: a node with one member repo, built in a temporary folder."""

from pathlib import Path

from conftest import write

from vic3tools import docs_lint

HEAD = '---\ntype: {type}\ndescription: "d"\nproject: p\ntags: [t]\n{extra}---\n'


def doc(path: Path, type_: str = "procedure", body: str = "# x\n", extra: str = "") -> Path:
    return write(path, HEAD.format(type=type_, extra=extra) + body)


def vault(tmp_path: Path) -> Path:
    node, mod = tmp_path / "node", tmp_path / "node" / "mod"
    write(node / "docs-check.toml", 'project = "p"\nmembers = ["mod"]\ndocs = ["docs/**"]\n')
    write(mod / "docs-check.toml", 'name = "mod"\nproject = "p"\nnode = "p"\ndocs = ["docs/**"]\n'
                                   'code_ext = [".txt"]\ncode_decision = \'(Д\\.\\d+)\'\n'
                                   'cover = ["common/**"]\ncode_roots = ["common/"]\n')
    doc(node / "docs" / "этапы" / "Этап 1. Начало.md", "phase", "# Этап 1\n\nрешение [[Д.1 — да]]\n",
        "status: active\ndate: 2026-10-29\n")
    doc(mod / "docs" / "решения" / "Д.1 — да.md", "decision", "# Да?\n", "status: active\ndate: 2026-10-29\n")
    doc(mod / "docs" / "код" / "a.md", "code", "# A\n\nСм. `common/a.txt`.\n", 'paths: ["common/a.txt"]\n')
    write(mod / "common" / "a.txt", "# Д.1\nx = 1\n")
    return node


def codes(res) -> list[tuple[str, str]]:
    return sorted((f.file, f.code) for f in res.failures)


def test_clean_vault(tmp_path):
    node = vault(tmp_path)
    res = docs_lint.check(node)
    assert codes(res) == []
    assert res.checked == {"node": 1, "mod": 2}


def test_findings(tmp_path):
    node = vault(tmp_path)
    mod = node / "mod"
    write(mod / "docs" / "bare.md", "# no header\n")
    doc(mod / "docs" / "links.md", body="[[Нет такого]] [[a#Нет раздела]] [x](a.md)\n")
    doc(mod / "docs" / "код" / "b.md", "code", "# B\n", 'paths: ["common/none.txt"]\n')
    write(mod / "common" / "b.txt", "# Д.9\n")  # no document's paths, an unknown decision
    write(mod / "docs" / "история" / "old.md", "no header, Д.1 as text — history keeps it\n[[Нет]]\n")
    res = docs_lint.check(mod)  # from the member: its documents, links over the whole vault
    assert ("common/b.txt", "uncovered") in [(f.file, f.code) for f in res.findings if f.note]  # not cover_strict
    assert codes(res) == [
        ("common/b.txt", "code_decision"),
        ("docs/bare.md", "no_header"),
        ("docs/links.md", "anchor"), ("docs/links.md", "link_nowhere"), ("docs/links.md", "md_link"),
        ("docs/история/old.md", "link_nowhere"),
        ("docs/код/b.md", "paths_missing"),
    ]


def test_mentions_fix(tmp_path):
    node = vault(tmp_path)
    p = doc(node / "mod" / "docs" / "код" / "c.md", "code", "# C\n\nПо Д.1, этап 1; в таблице:\n\n| Д.1 |\n",
            'paths: ["common/a.txt"]\n')
    res = docs_lint.check(node)
    assert [f.arg.split("@")[0] for f in res.failures if f.code == "mention"] == ["Д.1", "этап 1", "Д.1"]
    docs_lint.check(node, fix=True)
    assert p.read_text(encoding="utf-8").endswith(
        "По [[Д.1 — да|Д.1]], [[Этап 1. Начало|этап 1]]; в таблице:\n\n| [[Д.1 — да\\|Д.1]] |\n")
    assert codes(docs_lint.check(node)) == []


def test_ambiguous_and_known(tmp_path):
    node = vault(tmp_path)
    doc(node / "docs" / "README.md")
    doc(node / "mod" / "docs" / "README.md")
    doc(node / "mod" / "docs" / "e.md", body="[[README]]\n")
    res = docs_lint.check(node)
    assert codes(res) == [("docs/e.md", "link_ambiguous")]
    write(node / "mod" / "docs-check-known.txt", "docs/e.md: link_ambiguous README  # why\n")
    res = docs_lint.check(node)
    assert codes(res) == [] and res.known == 1


def test_standalone_repo(tmp_path):
    node = vault(tmp_path)
    mod = node / "mod"
    (node / "docs-check.toml").unlink()  # the repo's CI: no node around it
    doc(mod / "docs" / "f.md", body="[[Этап 1. Начало]]\n")
    res = docs_lint.check(mod)
    assert codes(res) == []
    assert {f.code for f in res.findings if f.note} == {"decision_idle", "link_outside", "orphan"}


def test_globs():
    assert docs_lint.matches("common/x/y.txt", ["common/**"])
    assert docs_lint.matches("common/x/y.txt", ["common/x"])
    assert docs_lint.matches("common/history/a/b.txt", ["common/history/*"])
    assert not docs_lint.matches("gui/a.gui", ["common/**"])
    assert docs_lint.matches("README.md", ["**/*.md"])
