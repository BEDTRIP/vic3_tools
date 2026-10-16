import json
import subprocess
import zipfile

import pytest
from conftest import write

from vic3tools import release


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def mod(tmp_path):
    m = tmp_path / "mymod"
    meta = {"name": "My Mod", "id": "com.example.mymod", "version": "1.0.0", "supported_game_version": "1.13.*",
            "short_description": "x", "picture": "thumbnail.png",
            "relationships": [{"rel_type": "dependency", "id": "com.example.cmf", "display_name": "CMF"}],
            "vic3tools": {"links": {"cmf": "workshop:3001", "set": "collection:42", "wiki": "https://example.org/w"}}}
    write(m / ".metadata/metadata.json", json.dumps(meta))
    (m / "thumbnail.png").write_bytes(b"\x89PNG" + b"0" * 100)
    write(m / "common/buildings/b.txt", "b = { }\n")
    write(m / "common/buildings/notes.md", "dev notes\n")
    write(m / "gui/_to_delete/old.gui", "x\n")
    write(m / "README.md", "readme\n")
    write(m / "docs/workshop/img/bank.png", "png")
    write(m / "docs/workshop/description.en.bbcode",
          "[h1]My Mod {version}[/h1]\n[img]{img:bank}[/img]\nNeeds [url={link:cmf}]CMF[/url], "
          "set [url={link:set}]here[/url], game {game_version}.\n")
    git(m, "init", "-q")
    git(m, "config", "user.email", "t@t")
    git(m, "config", "user.name", "t")
    git(m, "remote", "add", "origin", "https://github.com/someone/mymod.git")
    git(m, "add", "-A")
    git(m, "commit", "-qm", "first")
    return m


def test_select_keeps_only_what_the_game_reads(mod):
    sel = release.select(release.source_files(mod), "thumbnail.png")
    assert sel.keep == [".metadata/metadata.json", "common/buildings/b.txt", "thumbnail.png"]
    assert sel.left_out == {"*.md": 1, "_to_delete/": 1, "README.md": 1, "docs": 2}


def test_render_fills_images_links_and_versions(mod):
    meta = release.read_metadata(mod)
    tpl = (mod / "docs/workshop/description.en.bbcode").read_text(encoding="utf-8")
    text, missing = release.render(mod, tpl, meta, "release/1.0.0", "1.13.11")
    assert missing == []
    assert "[img]https://raw.githubusercontent.com/someone/mymod/release/1.0.0/docs/workshop/img/bank.png[/img]" in text
    assert "https://steamcommunity.com/sharedfiles/filedetails/?id=3001" in text
    assert "?id=42" in text and "My Mod 1.0.0" in text and "game 1.13.11" in text
    text, missing = release.render(mod, "{img:nope} {link:none}", meta, "release/1.0.0")
    assert missing == ["docs/workshop/img/nope.png", "link none (vic3tools.links in metadata.json)"]


def test_check(mod):
    probs = {p.key for p in release.check(mod, "1.13.11", {"com.example.cmf"})}
    assert probs == set()
    probs = {p.key for p in release.check(mod, "1.14.0", set())}
    assert probs == {"release_game_version", "release_dependency"}
    git(mod, "tag", "release/1.0.0")
    assert "release_same_version" in {p.key for p in release.check(mod, "1.13.11")}
    write(mod / "docs/workshop/description.en.bbcode", "x" * (release.DESC_LIMIT + 1))
    assert "release_desc_long" in {p.key for p in release.check(mod, "1.13.11", version="1.0.1")}
    (mod / "thumbnail.png").write_bytes(b"0" * (release.PREVIEW_LIMIT + 1))
    assert "release_picture_big" in {p.key for p in release.check(mod, "1.13.11", version="1.0.1")}


def test_build_done_and_change_note(mod, tmp_path):
    out = tmp_path / "out"
    b = release.build(mod, out, None, "1.13.11")
    assert b.new_item and b.files == 3
    content = b.out / "content"
    assert sorted(p.relative_to(content).as_posix() for p in content.rglob("*") if p.is_file()) == [
        ".metadata/metadata.json", "common/buildings/b.txt", "thumbnail.png"]
    vdf = (b.out / "upload.vdf").read_text(encoding="utf-8")
    assert '"publishedfileid"\t"0"' in vdf and '"visibility"\t"2"' in vdf and "First release." in vdf
    assert '"description"' not in vdf
    assert '"description"' in (b.out / "upload_with_description.vdf").read_text(encoding="utf-8")
    assert release.done(mod, b.out, "777", True) == [".metadata/metadata.json",
                                                     "docs/workshop/published/description.en.bbcode"]
    assert release.read_metadata(mod)["vic3tools"]["workshop_id"] == "777"
    git(mod, "add", "-A")
    git(mod, "commit", "-qm", "record")
    git(mod, "tag", "release/1.0.0")
    write(mod / "common/buildings/b.txt", "b = { level = 2 }\n")
    write(mod / "README.md", "more\n")
    git(mod, "add", "-A")
    git(mod, "commit", "-qm", "buildings: level 2")
    git(mod, "commit", "-qm", "docs only", "--allow-empty")
    b = release.build(mod, out, "1.0.1")
    vdf = (b.out / "upload.vdf").read_text(encoding="utf-8")
    assert '"publishedfileid"\t"777"' in vdf and '"visibility"' not in vdf
    assert (b.out / "changenote.txt").read_text(encoding="utf-8") == "1.0.1\n- buildings: level 2\n"
    built = json.loads((b.out / "content/.metadata/metadata.json").read_text(encoding="utf-8"))
    assert built["version"] == "1.0.1" and "vic3tools" not in built


def test_vdf_escapes():
    assert release.vdf({"title": 'a "b" \\ c'}) == '"workshopitem"\n{\n\t"title"\t"a \\"b\\" \\\\ c"\n}\n'


def test_zip_set(mod, tmp_path):
    other = tmp_path / "other"
    write(other / "events/e.txt", "e = 1\n")
    write(other / "notes.md", "x\n")
    path, n = release.zip_set([("My Mod", mod), ("Other: one", other)], tmp_path / "z" / "set.zip", "1.13.11", "Set")
    names = zipfile.ZipFile(path).namelist()
    assert "mod/Other_ one/events/e.txt" in names and "mod/My Mod/common/buildings/b.txt" in names
    assert not any(x.endswith(".md") for x in names) and n == 4
    readme = zipfile.ZipFile(path).read("README.txt").decode("utf-8")
    assert "Game version: 1.13.11" in readme and "  2. Other: one" in readme
