import pytest
from conftest import write

from vic3tools import cli
from vic3tools import save_queries as q
from vic3tools.save import Save

SAVE = """SAV0100
meta_data={
\tversion="1.13.11"
\tmods={ "Mod A" "Mod B" }
}
date=1841.1.1
country_manager={
\tdatabase={
\t\t3={
\t\t\tdefinition="GBR"
\t\t\tvariables={
\t\t\t\tdata={ {
\t\t\t\t\t\tflag=my_money
\t\t\t\t\t\tdata={
\t\t\t\t\t\t\ttype=value
\t\t\t\t\t\t\tidentity=150000
\t\t\t\t\t\t}
\t\t\t\t\t} {
\t\t\t\t\t\tflag=my_debt
\t\t\t\t\t\tdata={
\t\t\t\t\t\t\ttype=value
\t\t\t\t\t\t\tidentity=18446744073709451616
\t\t\t\t\t\t}
\t\t\t\t\t} }
\t\t\t}
\t\t}
\t\t5={
\t\t\tdefinition="FRA"
\t\t}
\t}
}
states={
\tdatabase={
\t\t10={
\t\t\tcountry=3
\t\t\tregion=1
\t\t}
\t\t11={
\t\t\tcountry=5
\t\t}
\t}
}
building_manager={
\tdatabase={
\t\t100={
\t\t\tbuilding=building_textile_mills
\t\t\tlevels=4

\t\t\tstate=10
\t\t\tgoods_sales=120.5
\t\t\tinput_goods={
\t\t\t\tgoods={
\t\t\t\t\t7={
\t\t\t\t\t\tvalue=2.5
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t\t101={
\t\t\tbuilding=building_manor_house
\t\t\tlevels=1
\t\t\tstate=10
\t\t}
\t\t102={
\t\t\tbuilding=building_company_acme
\t\t\tlevels=1
\t\t\tstate=11
\t\t}
\t\t103={
\t\t\tbuilding=building_textile_mills
\t\t\tlevels=9
\t\t\tstate=4294967295
\t\t}
\t}
}
building_ownership_manager={
\tdatabase={
\t\t1={
\t\t\tlevels=2
\t\t\tidentity={
\t\t\t\tbuilding=101
\t\t\t}
\t\t\tbuilding=100
\t\t}
\t\t2={
\t\t\tlevels=1
\t\t\tidentity={
\t\t\t\tbuilding=102
\t\t\t}
\t\t\tbuilding=100
\t\t}
\t\t3={
\t\t\tlevels=1
\t\t\tidentity={
\t\t\t\tcountry=3
\t\t\t}
\t\t\tbuilding=100
\t\t}
\t}
}
companies={
\tdatabase={
\t\t0={
\t\t\tcountry=5
\t\t\tbuilding=102
\t\t\tcompany_type=company_acme
\t\t}
\t}
}
"""


@pytest.fixture
def save(tmp_path, home):
    p = write(tmp_path / "test.v3", SAVE)
    s = Save.open(p)
    yield s
    s.close()


def test_index_and_entries(save):
    assert (save.date, save.version, save.mods) == ("1841.1.1", "1.13.11", ["Mod A", "Mod B"])
    assert [k for k, _s, _e in save.sections()] == ["meta_data", "country_manager", "states", "building_manager",
                                                    "building_ownership_manager", "companies"]
    assert save.countries() == {"3": "GBR", "5": "FRA"} and save.tag_id("FRA") == "5"
    assert save.states()["10"] == ("3", "1")
    b = save.entry("building_manager", "100")
    assert b.get("levels") == "4" and b.get("state") == "10"  # the blank line inside does not stop the reading
    assert b.block("input_goods").block("goods").block("7").get("value") == "2.5"


def test_variables(save):
    vals, _maps = q.variables(save.entry("country_manager", "3"), save.countries())
    assert vals == [("my_money", "1.5"), ("my_debt", "-1")]


def test_owners_buildings_companies_goods(save):
    h = q.holdings(save)
    assert "103" not in h.buildings  # a removed building
    lv = q.levels_by_class(h)
    assert dict(lv["GBR"]) == {"manor": 2, "f_comp": 1, "gov": 1}
    banks = q.levels_by_class(q.holdings(save, {"acme": ["company_ac*"]}))
    assert banks["GBR"]["f_comp"] == 1  # a foreign company stays foreign whatever its class
    rows = q.buildings_of(save, "building_textile_mills")
    assert rows["GBR"]["levels"] == 4 and rows["GBR"]["sales"] == 120.5
    assert dict(rows["GBR"]["owners"]) == {"manor": 2, "company": 1, "country": 1}
    assert q.company_holdings(save, "acme")[0]["levels"] == {"building_textile_mills": 1}
    assert q.goods_flows(save, "7")["GBR"]["input"] == 2.5


def test_cli_save(save, capsys):
    p = str(save.path)
    assert cli.main(["--lang", "en", "save", "owners", p]) == 0
    assert "levels at 1841.1.1" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "save", "vars", p, "GBR", "money"]) == 0
    assert "my_money = 1.5" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "save", "get", p, "country_manager", "FRA"]) == 0
    assert 'definition="FRA"' in capsys.readouterr().out


def test_binary_save_refused(tmp_path, home):
    p = tmp_path / "iron.v3"
    p.write_bytes(b"SAV0103\x00\x01PK\x03\x04binary")
    with pytest.raises(ValueError):
        Save.open(p)
