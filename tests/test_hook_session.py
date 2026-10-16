import json

from conftest import write

from vic3tools import hook, hook_session


def context(data: dict) -> str | None:
    out = hook_session.run(json.dumps(data))
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None


def setup(tmp_path, home, monkeypatch):
    van, mod = tmp_path / "van" / "game", tmp_path / "mods" / "mymod"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "common/x.txt", "a = 1\n")
    write(mod / "descriptor.mod", 'name = "m"\n')
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    monkeypatch.setattr(hook, "watched_roots", lambda: [van, mod])
    return van, mod


def test_menu_and_where_the_folder_is(tmp_path, home, monkeypatch):
    van, mod = setup(tmp_path, home, monkeypatch)
    t = context({"session_id": "s", "cwd": str(mod / "gui")})
    assert "`v3` (vic3tools) is installed" in t and "`refs X`" in t and "`gui set … --dry`" in t
    assert t.splitlines()[-1].startswith(f"This folder is inside {mod}")
    t = context({"session_id": "s", "cwd": str(tmp_path / "mods")})
    assert t.splitlines()[-1] == f"Under this folder, in the set `v3` reads: {mod}."
    t = context({"session_id": "s", "cwd": str(tmp_path / "elsewhere")})
    assert t.splitlines()[-1].startswith("- The game:")  # nothing to say about the folder
    assert context({}) is not None  # no cwd: the menu alone


def test_silent_without_the_game_or_on_bad_input(tmp_path, home, monkeypatch):
    monkeypatch.setattr(hook_session.paths, "resolve_roots",
                        lambda cfg: {"game": type("R", (), {"ok": False})()})
    assert hook_session.run(json.dumps({"cwd": str(tmp_path)})) == ""
    assert hook_session.run("not json") == ""
