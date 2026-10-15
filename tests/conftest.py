from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """An empty tools home, so no test reads or writes the real user config and cache."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("V3_HOME", str(h))
    monkeypatch.chdir(tmp_path)
    return h


def write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


@pytest.fixture
def game(tmp_path) -> Path:
    """A tiny fake game install: launcher settings and English / Russian localization."""
    root = tmp_path / "steam" / "steamapps" / "common" / "Victoria 3"
    write(root / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    loc = root / "game" / "localization"
    write(loc / "english" / "concepts_l_english.yml",
          'l_english:\n concept_institution:0 "Institution"\n'
          ' INSTITUTION_NEW_EFFECT:0 "Law [LawType.GetName] gives [INSTITUTION.GetName]"\n'
          ' BANKING: "Banking" # comment "with quotes"\n',
          encoding="utf-8-sig")
    write(loc / "russian" / "concepts_l_russian.yml",
          'l_russian:\n concept_institution:0 "Институт"\n BANKING: "Банковское дело"\n',
          encoding="utf-8-sig")
    return root
