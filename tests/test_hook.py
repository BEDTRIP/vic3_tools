import json

import pytest
from conftest import write

from vic3tools import hook
from vic3tools.core import vfs


@pytest.fixture
def env(tmp_path, home, monkeypatch):
    van, mod = tmp_path / "van" / "game", tmp_path / "mod"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "common/scripted_effects/e.txt", "my_effect = {\n\tx = 1\n}\n")
    write(mod / "common/scripted_effects/m.txt", "user = { my_effect = yes }\n")
    write(mod / "gui/big.gui", "window = {\n" + "".join(f'\ttextbox = {{ name = "t{i}" }}\n' for i in range(400))
          + "}\n")
    write(mod / "gui/small.gui", "window = {\n}\n")
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    ms = vfs.ModSet.from_dirs([mod])
    monkeypatch.setattr(vfs.ModSet, "from_playset", classmethod(lambda cls, name=None, cfg=None: ms))
    monkeypatch.setattr(hook, "watched_roots", lambda: [van, mod])
    return tmp_path, mod


def call(data: dict) -> str | None:
    out = hook.run(json.dumps(data))
    return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None


def test_grep_for_a_known_name_is_answered_once(env):
    tmp, mod = env
    d = {"session_id": "a", "tool_name": "Grep", "tool_input": {"pattern": r"\bmy_effect\b", "path": str(mod)}}
    reason = call(d)
    assert "v3 refs my_effect" in reason and "in user" in reason and "e.txt:1-3" in reason
    assert f"mod = {mod}" in reason
    assert call(d) is None  # the same search again goes through
    assert call({**d, "session_id": "b"}) is not None  # another session is asked again


def test_shell_search_and_parent_folder(env):
    tmp, _ = env
    d = {"session_id": "c", "tool_name": "Bash", "cwd": str(tmp),
         "tool_input": {"command": 'rg -n "my_effect" mod/common'}}
    assert "v3 def my_effect" in call(d)
    ps = {"session_id": "d", "tool_name": "PowerShell", "cwd": str(tmp),
          "tool_input": {"command": "Get-ChildItem -Recurse | Select-String -Pattern my_effect"}}
    assert call(ps) is not None


def test_what_passes(env):
    tmp, mod = env
    elsewhere = tmp / "other"
    elsewhere.mkdir()
    for d in (
        {"tool_name": "Grep", "tool_input": {"pattern": "my_effect", "path": str(elsewhere)}},  # not a mod folder
        {"tool_name": "Grep", "tool_input": {"pattern": "my_eff.*", "path": str(mod)}},  # a regex, not a name
        {"tool_name": "Grep", "tool_input": {"pattern": "unknown_name", "path": str(mod)}},  # the index lacks it
        {"tool_name": "Grep", "tool_input": {"pattern": "my_effect", "path": str(mod), "glob": "*.md"}},
        {"tool_name": "Bash", "cwd": str(mod), "tool_input": {"command": "git log --oneline"}},
        {"tool_name": "Read", "tool_input": {"file_path": str(mod / "gui/small.gui")}},
        {"tool_name": "Read", "tool_input": {"file_path": str(mod / "gui/big.gui"), "offset": 10, "limit": 20}},
    ):
        assert call({"session_id": "e", **d}) is None, d
    assert hook.run("not json") == ""


def test_whole_read_of_a_big_file_gets_the_outline(env):
    _, mod = env
    d = {"session_id": "f", "tool_name": "Read", "tool_input": {"file_path": str(mod / "gui/big.gui")}}
    reason = call(d)
    assert "402 lines" in reason and "window  1-402" in reason
    assert call(d) is None


def test_identifier():
    assert hook.identifier(r"\bzz_ef_x\b") == "zz_ef_x"
    assert hook.identifier("^my_effect\\s*=") == "my_effect"
    assert hook.identifier("ev.12") == "ev.12"
    assert hook.identifier("hello") is None and hook.identifier("a|b_c") is None
    assert hook.shell_identifier('grep -rn --include="*.txt" "my_var_1" common/') == "my_var_1"
    assert hook.shell_identifier("ls | Select-String my_var_1") == "my_var_1"
    # words inside a heredoc body or a string are not commands
    heredoc = "cat > a.gui <<'EOF'\nraw_text = \"none Rg x\"\nmy_var_1 rg here\nEOF\nv3 lint"
    assert hook._search_at(heredoc) is None and hook._search_at('echo "use grep my_var_1"') is None
    assert hook.shell_identifier(heredoc + "\ngrep -n my_var_2 common/") == "my_var_2"
    assert hook._search_at("ls Rg common/") is None
    for p in (r"my_list_\d+", "my_list_N", "my_list_.*"):
        assert hook.identifier(p) == "my_list_*", p


def test_numbered_family_and_prefix(env):
    _, mod = env
    write(mod / "common/script_values/v.txt",
          "v1 = { every_in_list = { variable = my_buyer_list_1 } }\n"
          "v2 = { every_in_list = { variable = my_buyer_list_2 } }\n")
    for pattern in ("my_buyer_list_N", "my_buyer_list_"):
        d = {"session_id": pattern, "tool_name": "Grep", "tool_input": {"pattern": pattern, "path": str(mod)}}
        assert "2 name(s) match my_buyer_list_*" in call(d), pattern
