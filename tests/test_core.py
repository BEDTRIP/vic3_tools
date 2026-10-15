from pathlib import Path

from conftest import write

from vic3tools.core import loc, paths, vdf


def test_vdf_nested_and_escapes():
    data = vdf.loads('"libraryfolders"\n{\n "0"\n {\n  "path" "C:\\\\Games\\\\Steam" // note\n'
                     '  "apps" { "529340" "1" }\n }\n}\n')
    entry = data["libraryfolders"]["0"]
    assert entry["path"] == "C:\\Games\\Steam"
    assert entry["apps"] == {"529340": "1"}


def test_steam_libraries_and_game(tmp_path, game):
    steam = tmp_path / "steam"
    other = tmp_path / "lib2"
    other.mkdir()
    write(steam / "steamapps" / "libraryfolders.vdf",
          f'"libraryfolders" {{ "0" {{ "path" "{steam.as_posix()}" }} "1" {{ "path" "{other.as_posix()}" }} }}')
    assert paths.steam_libraries(steam) == [steam, other]
    assert paths.find_game_library([steam]) == steam
    assert paths.game_version(game) == "1.13.11"


def test_config_project_overrides_user(home, tmp_path):
    write(home / "vic3tools.toml", 'lang = "ru"\n[roots]\ngame = "A"\ndocuments = "D"\n')
    project = tmp_path / "proj" / "sub"
    project.mkdir(parents=True)
    write(tmp_path / "proj" / "vic3tools.toml", '[roots]\ngame = "B"\n')
    cfg = paths.load_config(project)
    assert cfg.get("roots", "game") == "B"
    assert cfg.get("roots", "documents") == "D"
    assert cfg.values["lang"] == "ru"
    assert cfg.source_of("roots", "game") == tmp_path / "proj" / "vic3tools.toml"


def test_write_user_config_roundtrip(home):
    f = paths.write_user_config({"game": Path(r"C:\it's here"), "documents": Path("/docs")}, "en")
    cfg = paths.load_config(home)
    assert cfg.files == [f]
    assert cfg.get("roots", "game") == r"C:\it's here"
    assert cfg.values["lang"] == "en"


def test_resolve_roots_config_wins(home, game, monkeypatch):
    monkeypatch.setattr(paths, "detect_roots", lambda: {n: paths.Root(None, "not found") for n in paths.ROOT_NAMES})
    write(home / "vic3tools.toml", f"[roots]\ngame = '{game}'\n")
    roots = paths.resolve_roots(paths.load_config())
    assert roots["game"].ok and roots["game"].source.startswith("config")
    assert not roots["workshop"].ok


def test_loc_reader(game):
    entries = list(loc.read_file(game / "game/localization/english/concepts_l_english.yml"))
    assert [(e.key, e.line) for e in entries] == [("concept_institution", 2), ("INSTITUTION_NEW_EFFECT", 3),
                                                  ("BANKING", 4)]
    assert entries[2].text == "Banking"


def test_loc_replace_wins(tmp_path):
    root = tmp_path / "localization"
    write(root / "english" / "replace" / "a_l_english.yml", 'l_english:\n K: "new"\n')
    write(root / "english" / "z_l_english.yml", 'l_english:\n K: "old"\n')
    assert loc.read_language(root, "english")["K"].text == "new"
