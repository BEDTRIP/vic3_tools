import json

from conftest import write

from vic3tools import mod_history as mh


def test_snapshot_history_diff(tmp_path):
    repo = tmp_path / "hist"
    a = tmp_path / "ws" / "3001"
    write(a / ".metadata/metadata.json", json.dumps({"id": "3001", "version": "1.0"}))
    write(a / "common/x.txt", "x = 1\n")
    own = tmp_path / "own"
    write(own / "common/y.txt", "y = 1\n")
    (own / ".git").mkdir()
    game = tmp_path / "game"
    write(game / "game/common/v.txt", "v = 1\n")
    write(game / "game/gfx/big.dds", "binary")

    snaps = mh.snapshot([("Mod A", a), ("Own", own)], game, "1.13.11", vanilla=True, repo=repo)
    assert [(s.name, s.folder, s.changed) for s in snaps] == [("vanilla", "_vanilla", 1), ("Mod A", "3001", 2)]
    assert not (repo / "_vanilla/gfx").exists()  # only the text folders of the game
    assert [s.changed for s in mh.snapshot([("Mod A", a)], None, "1.13.11", repo=repo)] == [0]  # nothing new

    write(a / ".metadata/metadata.json", json.dumps({"id": "3001", "version": "1.1"}))
    write(a / "common/x.txt", "x = 2\n")
    write(a / "common/z.txt", "z = 1\n")
    assert [s.changed for s in mh.snapshot([("Mod A", a)], None, "1.13.12", repo=repo)] == [3]
    log = mh.history(repo, "3001")
    assert len(log) == 2 and log[0].endswith("Mod A 1.1 — game 1.13.12")
    assert mh.find_folder(repo, "mod a") == "3001"
    d = mh.diff(repo, "3001")
    assert "common/x.txt" in d and "common/z.txt" in d
    assert "+x = 2" in mh.diff(repo, "3001", stat=False)
