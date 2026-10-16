import pytest

from vic3tools import bench, bridge, cli_bench

PIL = pytest.importorskip("PIL.Image")


def _png(path, color, patch=None):
    im = PIL.new("RGB", (200, 100), color)
    if patch:
        x0, y0, x1, y1, c = patch
        for x in range(x0, x1):
            for y in range(y0, y1):
                im.putpixel((x, y), c)
    im.save(path)
    return path


def test_box_fractions_and_pixels():
    assert bench.box((200, 100), None) == (0, 0, 200, 100)
    assert bench.box((200, 100), "0.5,0,1,0.5") == (100, 0, 200, 50)
    assert bench.box((200, 100), "10,20,300,90") == (10, 20, 200, 90)
    with pytest.raises(ValueError):
        bench.box((200, 100), "1,2,3")


def test_diff_and_cut(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10))
    b = _png(tmp_path / "b.png", (10, 10, 10), (50, 20, 60, 30, (250, 250, 250)))
    d = bench.diff(a, b, out=tmp_path / "d.png")
    assert d.bbox == (50, 20, 60, 30) and d.changed == pytest.approx(100 / 20000) and d.image.is_file()
    assert bench.diff(a, b, crop="0,0,40,100").bbox is None  # the change is outside the crop
    assert bench.diff(a, _png(tmp_path / "c.png", (14, 14, 14))).bbox is None  # under the tolerance
    cut = bench.cut(b, "0.25,0,0.5,0.5", tmp_path / "cut.png")
    assert PIL.open(cut).size == (50, 50)


def test_find_shot(tmp_path, home):
    d = bench.bench_dir() / "b1016_000000_x"
    d.mkdir(parents=True)
    shot = _png(d / "x.png", (0, 0, 0))
    assert cli_bench.find_shot("x") == shot and cli_bench.find_shot(str(shot)) == shot
    with pytest.raises(FileNotFoundError):
        cli_bench.find_shot("nothing")


def test_bridge_allows_reads_only():
    assert bridge.check(["refs", "my_var"]) is None
    assert bridge.check(["gui", "set", "gui/a.gui:3", "size={ 1 2 }", "--dry"]) is None
    assert bridge.check(["bench", "shot", "x"]) is None
    assert "only with --dry" in bridge.check(["gui", "set", "gui/a.gui:3", "size={ 1 2 }"])
    assert "writes into a mod" in bridge.check(["lint", "--baseline"])
    assert "not allowed" in bridge.check(["setup"]) and bridge.check([]) == "no command"
    assert bridge.run(["hook", "pre-tool-use"]).startswith("refused:")


def test_bridge_runs_v3(home):
    out = bridge.run(["glossary", "--help"])
    assert out.startswith("exit 0") and "glossary" in out
