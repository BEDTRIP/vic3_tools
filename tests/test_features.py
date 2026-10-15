import json

from conftest import write

from vic3tools import cli, docs_check, glossary, i18n


def test_glossary_build_and_search(home, game):
    db, count = glossary.build(game, "1.13.11")
    assert count == 2  # the template entry with [...] is not a term
    hits = glossary.search("институт", db)
    assert hits[0].key == "concept_institution" and hits[0].texts["en"] == "Institution"
    assert glossary.search("BANK", db)[0].texts["ru"] == "Банковское дело"
    assert glossary.search("index", None)[0].section == "tools"


def test_is_term():
    assert glossary.is_term("Banking")
    assert not glossary.is_term("[Country.GetName] gains")
    assert not glossary.is_term("one two three four five six seven")


def test_catalogs_have_the_same_keys():
    assert set(i18n.catalog("en")) == set(i18n.catalog("ru"))


def test_t_language_and_fallback(monkeypatch):
    i18n.set_lang("ru")
    assert i18n.t("not_found") == "не найдено"
    assert i18n.t("no_such_key") == "no_such_key"
    i18n.set_lang(None)
    monkeypatch.setenv("V3_LANG", "en")
    assert i18n.t("game_version", version="1.0") == "game version: 1.0"


def test_docs_check_ru(tmp_path):
    src = write(tmp_path / "docs" / "guide.md", "# Guide\n")
    write(tmp_path / "docs" / "other.md", "# Other\n")
    tr = write(tmp_path / "docs" / "ru" / "guide.md", docs_check.mark_line(tmp_path, src) + "\n# Руководство\n")
    problems, checked = docs_check.check(tmp_path)
    assert checked == 1 and [p.kind for p in problems] == ["untranslated"]
    src.write_text("# Guide, changed\n", encoding="utf-8")
    assert [p.kind for p in docs_check.check(tmp_path)[0]] == ["stale", "untranslated"]
    tr.write_text("# no mark\n", encoding="utf-8")
    assert docs_check.check(tmp_path)[0][0].kind == "no_mark"


def test_blob_hash_matches_git():
    import hashlib
    assert hashlib.sha1(b"blob 6\0hello\n").hexdigest() == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_cli_where_json(home, game, capsys, monkeypatch):
    monkeypatch.setattr(cli.paths, "detect_roots",
                        lambda: {n: cli.paths.Root(None, "not found") for n in cli.paths.ROOT_NAMES})
    write(home / "vic3tools.toml", f"[roots]\ngame = '{game}'\n")
    assert cli.main(["where", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["game_version"] == "1.13.11"
    assert out["roots"]["game"]["exists"] and not out["roots"]["documents"]["exists"]


def test_cli_setup_then_glossary(home, game, capsys, monkeypatch):
    monkeypatch.setattr(cli.paths, "detect_roots",
                        lambda: {n: cli.paths.Root(None, "not found") for n in cli.paths.ROOT_NAMES})
    write(home / "vic3tools.toml", f"[roots]\ngame = '{game}'\n")
    assert cli.main(["--lang", "en", "setup"]) == 0
    assert (home / "cache" / "glossary-1.13.11.sqlite").is_file()
    assert "game = " in (home / "vic3tools.toml").read_text(encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["--lang", "en", "glossary", "Institution"]) == 0
    assert "Институт" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "doctor"]) == 1  # workshop, documents and tiger are missing
