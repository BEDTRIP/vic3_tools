from conftest import write

from vic3tools import logs

ERR = """[10:00:01][jomini_effect.cpp:120]: Variable 'my_var' is used but is never set
[10:00:02][reader.cpp:216]: Error: "Unexpected: }" in file: "common/scripted_effects/a.txt" near line: 7
[10:00:02][jomini_script.cpp:9]: Script error in 'common/scripted_effects/a.txt:12'
  Script location: common/scripted_effects/a.txt:12
[10:00:03][x.cpp:1]: EFW|1836.1.8|GBR|money 5
"""
ERR1 = "[09:59:59][jomini_effect.cpp:120]: Variable 'other_var' is used but is never set\n"
DEBUG = """[23:59:50][on_actions.cpp:1]: Party formed: January 1, 1836
[23:59:58][on_actions.cpp:1]: Party formed: January 31, 1836
[00:00:06][on_actions.cpp:1]: Party formed: March 1, 1836
[00:00:14][on_actions.cpp:1]: Party formed: марта 31, 1836
"""


def test_files_order_and_parts(tmp_path):
    write(tmp_path / "error.1.log", ERR1)
    write(tmp_path / "error.log", ERR)
    write(tmp_path / "errparts/000_error.1.log", ERR1)  # the same file kept by the run script: read once
    assert [p.name for p in logs.files(tmp_path, "error")] == ["000_error.1.log", "error.log"]
    recs = list(logs.records(tmp_path, "error"))
    assert len(recs) == 5 and recs[3].text.endswith("Script location: common/scripted_effects/a.txt:12")


def test_summary_sites_compare(tmp_path):
    base, run = tmp_path / "base", tmp_path / "run"
    write(base / "error.log", ERR1)
    write(run / "error.log", ERR)
    s = logs.summarize(run, "error", skip=r"(^|: )EF[A-Z]{1,2}\|")
    assert s.records == 3 and s.skipped == 1
    assert s.families["Variable '…' is used but is never set"] == 1
    assert ("Variable", "my_var", "used") in s.unused
    total, places, per_file = logs.sites(run)
    assert total == 4 and per_file["common/scripted_effects/a.txt"] == 2
    assert {p for p, _m in places} == {"common/scripted_effects/a.txt:7", "common/scripted_effects/a.txt:12"}
    d = logs.compare(base, run, "error")
    assert [k for k, _n in d.gone] == [] and len(d.new) == 3  # the same family in both: not new


def test_mod_lines_collapse(tmp_path):
    names = ["Чили", "Куба", "Оман", "Сербия", "Любек", "Гамбург", "Египет", "Бавария", "Новая Шотландия", "Перу"]
    lines = [f"[10:00:0{i % 10}][jomini_effect_impl.cpp:454]: x.txt:9: EFD|марта {i}, 1836|{c}|asset|kind {i}|r -{i}"
             for i, c in enumerate(names)]
    lines += [f"[10:00:01][jomini_effect_impl.cpp:454]: x.txt:9: EFD|мая 1, 1836|{c}|budget|inc {i}"
              for i, c in enumerate(names[:2])]
    write(tmp_path / "debug.log", "\n".join(lines) + "\n")
    s = logs.summarize(tmp_path, "debug")
    assert s.families == {"x.txt:N: EFD|DATE|…|asset|kind N|r N": 10, "x.txt:N: EFD|DATE|…|budget|inc N": 2}
    assert logs.family("range 1-2, m3") == "range N-N, mN"


def test_real_lines(tmp_path):
    f = write(tmp_path / "e.txt", "my_effect = {\n\n\t# a comment\n\tset_variable = x\n}\nother = {\n\ta = b\n}\n")
    assert logs.real_lines(f, 2) == [4]  # error.log says 2: the blank and the comment line before are not counted
    assert logs.real_lines(f, 6) == [6] and logs.real_lines(f, 7) == [7]  # the count restarts at a top key


def test_speed(tmp_path):
    write(tmp_path / "debug.log", DEBUG)
    pts = logs.speed_points(tmp_path)
    assert [s for _g, s in pts] == [86390, 86398, 86406, 86414]  # past midnight the clock goes on
    assert round(logs.slope(pts), 2) == round(24 / 90 * 30, 2)
