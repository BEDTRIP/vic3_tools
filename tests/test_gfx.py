import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from vic3tools.gfx import cards, dds  # noqa: E402


def test_dds_roundtrip_with_mips(tmp_path):
    img = Image.new("RGBA", (64, 32), (10, 200, 30, 128))
    p = dds.write(img, tmp_path / "a.dds")
    i = dds.info(p)
    assert (i.width, i.height, i.format, i.mips) == (64, 32, "BGRA8", 7)
    assert i.vanilla_like
    assert Image.open(p).convert("RGBA").tobytes() == img.tobytes()
    # header + 64*32 + 32*16 + ... + 1*1 (each level halves, never below 1)
    sizes = [(64, 32), (32, 16), (16, 8), (8, 4), (4, 2), (2, 1), (1, 1)]
    assert p.stat().st_size == 128 + sum(w * h * 4 for w, h in sizes)


def test_dds_no_mips(tmp_path):
    p = dds.write(Image.new("RGBA", (8, 8)), tmp_path / "b.dds", mips=False)
    assert dds.info(p).mips == 1 and not dds.info(p).vanilla_like


def test_card_roundtrip(tmp_path):
    c = cards.Card.new("gfx/interface/icons/goods_icons/x.dds", "goods", prompt='a "bundle"\nof notes',
                       samples=["gfx/a.dds", "fork:gfx/b.dds"])
    p = c.save(tmp_path / "gfx_src" / "goods" / "x.toml")
    back = cards.Card.load(p)
    assert back.prompt == 'a "bundle"\nof notes'
    assert back.samples == ["gfx/a.dds", "fork:gfx/b.dds"]
    assert back.size == [256, 256] and back.post == ["cutout"] and back.mips is True
    assert back.mod_root() == tmp_path.resolve()
    assert back.source.name == "x.png" and back.variants.name == "x.variants"


def test_card_unknown_kind():
    with pytest.raises(ValueError):
        cards.Card.new("x.dds", "nope")


def test_fit_trims_and_centres():
    img = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (100, 400, 900, 600))  # a wide bar off-centre
    out = cards.fit(img, (256, 256))
    assert out.size == (256, 256)
    x0, y0, x1, y1 = out.getbbox()
    assert x1 - x0 > 230 and abs((x0 + x1) / 2 - 128) <= 1 and abs((y0 + y1) / 2 - 128) <= 1


def test_tint_keeps_alpha_and_ramps():
    img = Image.new("RGBA", (3, 1))
    img.putpixel((0, 0), (0, 0, 0, 255))
    img.putpixel((1, 0), (128, 128, 128, 100))
    img.putpixel((2, 0), (255, 255, 255, 0))
    out = cards.tint(img, "bronze")
    dark, mid, light = (out.getpixel((x, 0)) for x in range(3))
    assert dark[:3] == cards._rgb(cards.TINTS["bronze"][0]) and light[:3] == cards._rgb(cards.TINTS["bronze"][2])
    assert (dark[3], mid[3], light[3]) == (255, 100, 0)
    assert sum(dark[:3]) < sum(mid[:3]) < sum(light[:3])


def test_fit_opaque_covers():
    img = Image.new("RGBA", (1536, 1088), (200, 100, 50, 255))
    out = cards.fit(img, (1536, 1024), opaque=True)
    assert out.size == (1536, 1024) and out.getextrema()[3] == (255, 255)
