import json

import pytest
from conftest import write

from vic3tools import cli
from vic3tools.compat import holes, index, set_audits
from vic3tools.core import vfs
from vic3tools.gui import names


@pytest.fixture
def chain(tmp_path, home):
    van, a, b, build = tmp_path / "van" / "game", tmp_path / "a", tmp_path / "b", tmp_path / "build"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "common/buildings/b.txt", "building_mill = {\n\tproduction_method_groups = { pmg_base }\n}\n")
    write(van / "common/prestige_goods/p.txt",
          "pg_1 = { base_good = grain }\npg_2 = { base_good = grain }\npg_3 = { base_good = grain }\n")
    write(van / "events/v.txt", "namespace = v\nv.1 = { type = country_event }\n")
    write(a / "common/buildings/a.txt",
          "INJECT:building_mill = {\n\tproduction_method_groups = { pmg_a_extra }\n}\n"
          "building_a_new = {\n\townership_type = self\n\tproduction_method_groups = { pmg_x }\n}\n")
    write(a / "common/prestige_goods/a.txt", "pg_a = { base_good = grain }\n")
    write(a / "common/laws/l.txt", "law_a = { group = lawgroup_shared }\nlaw_b = { group = lawgroup_only_a }\n")
    write(a / "events/a.txt", "namespace = v\nv.1 = { type = country_event }\n")
    write(b / "common/buildings/b.txt",
          "building_mill = {\n\tproduction_method_groups = { pmg_base pmg_b }\n}\n")
    write(b / "common/laws/l.txt", "law_c = { group = lawgroup_shared }\n")
    write(b / "common/company_types/c.txt", "company_b = { building_types = { building_mill } }\n")
    write(build / "common/buildings/z1.txt", "building_mill = { production_method_groups = { pmg_base } }\n")
    write(build / "common/buildings/z2.txt", "REPLACE:building_mill = { production_method_groups = { pmg_base } }\n")
    write(build / "localization/english/x_l_english.yml", 'l_english:\n K: "1"\n')
    write(build / "localization/english/y_l_english.yml", 'l_english:\n K: "2"\n')
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    return vfs.ModSet.from_dirs([a, b, build])


def test_holes(chain):
    srcs = holes.sources(chain)
    new = holes.new_content(srcs)
    rows = [(k, who) for c, k, _d, who in new["a"] if c == "common/buildings"]
    assert rows == [("building_a_new", [])]  # nobody else mentions it
    assert {k for c, k, _d, _w in new["a"] if c == "common/laws"} == {"law_a", "law_b"}
    lost = {k: (last.label, dict(x)) for k, last, x in holes.eaten(srcs, "pmg")}
    # b's bare body after a's INJECT drops pmg_a_extra; the build's REPLACE drops b's pmg_b too
    assert lost["building_mill"] == ("build", {"pmg_a_extra": {"a"}, "pmg_b": {"b"}})
    eco = holes.outside_economy(srcs, ["pmg_market_*"])
    assert [(k, m) for _l, k, m, _o in eco] == [("building_a_new", ["pmg_market_*"])]
    later = holes.builds_vs_later(srcs, {"a"})
    assert later["a"]["b"] == {"common/buildings": ["building_mill"]}  # b's bare body wipes a's INJECT


def test_set_audits(chain):
    order = set_audits.prestige(chain)
    assert [k for k, _m, _f in order["grain"]] == ["pg_1", "pg_2", "pg_3", "pg_a"]  # pg_a is the dead 4th
    assert list(set_audits.event_ids(chain)) == ["v.1"]
    d = set_audits.duplicates(index.build(chain.mods[3]))
    assert [(c, k) for c, k, _w in d["records"]] == [("common/buildings", "building_mill")]
    assert [(lang, k) for lang, k, _w in d["loc"]] == [("english", "K")]
    cats, paths = set_audits.against_vanilla(index.build(chain.mods[0]), index.build(chain.mods[2]))
    assert dict(cats["common/buildings"]) == {"overrides": 1} and paths == ["common/buildings/b.txt"]
    a, b = set_audits.lawgroups(chain.mods[1]), set_audits.lawgroups(chain.mods[2])
    assert set(a) - set(b) == {"lawgroup_only_a"}


def test_cli_audits(chain, capsys):
    dirs = [str(m.path) for m in chain.mods[1:]]
    assert cli.main(["--lang", "en", "audit", "prestige", "--mods", *dirs]) == 1
    assert "dead: pg_a (a)" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "audit", "holes", "--only", "new", "--mods", *dirs]) == 0
    assert "building_a_new" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "audit", "lawgroups", dirs[0], "--other", dirs[1], "--json", "--mods", *dirs]) == 0
    assert "lawgroup_only_a" in json.dumps(json.loads(capsys.readouterr().out))


def test_gui_names(tmp_path):
    write(tmp_path / "a/gui/p.gui", 'types T {\n\ttype t1 = widget {}\n}\nwindow = {\n\tname = "w1"\n'
                                    '\twidget = { name = "w2" }\n}\n')
    write(tmp_path / "b/gui/p.gui", 'window = {\n\tname = "w1"\n}\ntexticon = { icon = coin }\n')
    r = names.compare(names.identifiers(tmp_path / "a"), names.identifiers(tmp_path / "b"))
    assert r["name"] == {"shared": ["w1"], "only_a": ["w2"], "only_b": []}
    assert r["type"]["only_a"] == ["t1"] and r["icon"]["only_b"] == ["coin"]
