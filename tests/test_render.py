import pytest
from conftest import write

from vic3tools.core import vfs
from vic3tools.gui import render
from vic3tools.index import query

PIL = pytest.importorskip("PIL.Image")

WIDGETS = """types T {
\ttype my_panel = widget {
\t\tsize = { 200 100 }
\t\tflowcontainer = {
\t\t\tdirection = vertical
\t\t\tmargin = { 10 5 }
\t\t\tspacing = 4
\t\t\ticon = { size = { 20 10 } texture = "gfx/red.png" parentanchor = right }
\t\t\ticon = { size = { 30 10 } texture = "gfx/red.png" }
\t\t\ticon = { size = { 30 10 } visible = no }
\t\t}
\t\thbox = {
\t\t\tposition = { 0 60 }
\t\t\tsize = { 100 20 }
\t\t\ticon = { size = { 20 20 } texture = "gfx/red.png" }
\t\t\texpand = {}
\t\t\ticon = { size = { 20 20 } texture = "gfx/red.png" }
\t\t}
\t\ticon = { size = { 10 10 } parentanchor = bottom|right texture = "gfx/red.png" }
\t}
}
"""


@pytest.fixture
def rd(tmp_path, home):
    van, m1 = tmp_path / "van" / "game", tmp_path / "m1"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "gui/p.gui", WIDGETS)
    (van / "gfx").mkdir(parents=True)
    PIL.new("RGBA", (4, 4), (255, 0, 0, 255)).save(van / "gfx/red.png")
    write(m1 / "gui/x.gui", "")
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    si = query.SetIndex.open(vfs.ModSet.from_dirs([m1]))
    yield render.Renderer(si)
    si.close()


def test_layout(rd):
    r = rd.res.expand(rd.res.find("type", "my_panel"))
    b = rd.layout(r, 1920, 1080)
    assert (b.w, b.h) == (200, 100)
    flow, box, corner = b.children
    assert (flow.w, flow.h) == (50, 34)  # 30 wide + margins 10 × 2; 10 + 4 + 10 + margins 5 × 2; the hidden one out
    assert [(c.x, c.y) for c in flow.children] == [(20, 5), (10, 19)]  # the narrow one aligned right
    assert [(round(c.x), c.w) for c in box.children] == [(0, 20), (20, 60), (80, 20)]  # expand takes what is left
    assert (corner.x, corner.y) == (190, 90)  # bottom|right


def test_paint(rd):
    img, _b = rd.render(rd.res.find("type", "my_panel"), pad=0)
    assert img.size == (200, 100)
    assert img.getpixel((25, 7))[:3] == (255, 0, 0) and img.getpixel((5, 2))[3] == 0
    assert img.getpixel((195, 95))[:3] == (255, 0, 0)


def test_nine_slice():
    src = PIL.new("RGBA", (10, 10), (0, 0, 255, 255))
    for x in range(10):
        src.putpixel((x, 0), (255, 0, 0, 255))
    out = render._nine(src, 2, 2, 40, 30)
    assert out.size == (40, 30)
    assert out.getpixel((20, 0))[:3] == (255, 0, 0) and out.getpixel((20, 15))[:3] == (0, 0, 255)
