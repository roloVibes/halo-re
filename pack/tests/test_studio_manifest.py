"""Studio contribution tests — the two sections and their bundle panels.

Covers the manifest declaration of BOTH sections (Reverse engineering:
findings browser + counts/table/feed; Craft & rebuild: studies browser +
counts/table/feed), the studio-script grant, palette routes into both
sections, config_form, the counts panels being TABLES (markdown cannot
read the data folder), the browser modules' CSP hygiene, and node
syntax checks when node exists.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

_PACK = Path(__file__).resolve().parent.parent
_JS = _PACK / "studio" / "findings.js"
_CRAFT_JS = _PACK / "studio" / "craft.js"


def _manifest() -> dict:
    try:
        import yaml
    except ImportError:
        pytest.skip("SKIPPED -- pyyaml not installed")
    return yaml.safe_load((_PACK / "pack.yaml").read_text())


def _sections() -> dict:
    m = _manifest()
    return {s["id"]: s for s in m["contributes"]["studio"]["sections"]}


def test_manifest_declares_two_sections():
    sections = _sections()
    assert set(sections) == {"re", "craft"}, sections.keys()
    assert sections["re"]["title"] == "Reverse engineering"
    assert sections["craft"]["title"] == "Craft & rebuild"


def test_re_section_bundle_and_counts():
    panels = {p["id"]: p for p in _sections()["re"]["panels"]}
    assert panels["browser"]["kind"] == "bundle"
    assert panels["browser"]["source"] == "studio/findings.js"
    assert (_PACK / "studio" / "findings.js").exists()
    # the counts panel is a TABLE reading the data folder (markdown cannot)
    assert panels["counts"]["kind"] == "table"
    assert panels["counts"]["source"] == "data:findings/counts.json"
    m = _manifest()
    assert "studio-script" in m["permissions"]


def test_craft_section_bundle_and_counts():
    panels = {p["id"]: p for p in _sections()["craft"]["panels"]}
    assert panels["studies"]["kind"] == "bundle"
    assert panels["studies"]["source"] == "studio/craft.js"
    assert (_PACK / "studio" / "craft.js").exists()
    assert panels["craft-counts"]["kind"] == "table"
    assert panels["craft-counts"]["source"] == "data:craft/counts.json"
    # the craft studies table reads the data folder too
    assert panels["craft-table"]["source"] == "data:craft/studies.json"
    # the study event kind is declared with its schema
    kinds = {e["kind"]: e for e in _manifest()["contributes"]["events"]}
    assert "re.craft.study" in kinds
    assert (_PACK / kinds["re.craft.study"]["schema"]).exists()


def test_manifest_palette_routes_resolve():
    m = _manifest()
    studio = m["contributes"]["studio"]
    sections = {s["id"]: {p["id"] for p in s["panels"]} for s in studio["sections"]}
    routed = set()
    for line in studio.get("palette", []):
        action = line["action"]
        assert action.startswith("route:")
        target = action[len("route:"):]
        sec = target.split("/")[0]
        assert sec in sections, f"palette route to an unknown section: {action}"
        routed.add(sec)
        if "/" in target:
            assert target.split("/")[1] in sections[sec], f"palette route to nothing: {action}"
    assert routed == set(sections), "every section should have a palette line"
    assert studio.get("config_form") is True


def test_browser_js_targets_this_pack():
    js = _JS.read_text()
    assert "api/pack/halo-re/data/findings/summary.json" in js
    assert "halo-hacker" not in js, "the browser must not point at the sibling pack"


def test_craft_js_targets_the_craft_data():
    js = _CRAFT_JS.read_text()
    assert "api/pack/halo-re/data/craft/studies.json" in js
    assert "halo-hacker" not in js


def test_craft_js_csp_hygiene():
    import re
    js = _CRAFT_JS.read_text()
    assert re.search(r"export\s+(function\s+mount|\{\s*mount)", js), "no mount export"
    assert "innerHTML" not in js, "CSP/XSS: no innerHTML anywhere"
    assert "<style" not in js, "CSP: no inline style elements"
    assert 'style="' not in js, "CSP: no style attributes"
    assert 'createElement("script")' not in js and "createElement('script')" not in js


def test_craft_js_node_syntax_check():
    node = shutil.which("node")
    if not node:
        pytest.skip("SKIPPED -- node not on PATH (ES module syntax check)")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(_CRAFT_JS.read_text())
        path = fh.name
    r = subprocess.run([node, "--check", path], capture_output=True, text=True)
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"


def test_browser_js_csp_hygiene():
    js = _JS.read_text()
    assert "export function mount" in js
    assert "innerHTML" not in js, "CSP/XSS: no innerHTML anywhere"
    assert "<style" not in js, "CSP: no inline style elements"
    assert 'style="' not in js, "CSP: no style attributes"
    assert 'createElement("script")' not in js and "createElement('script')" not in js


def test_browser_js_node_syntax_check():
    node = shutil.which("node")
    if not node:
        pytest.skip("SKIPPED -- node not on PATH (ES module syntax check)")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(_JS.read_text())
        path = fh.name
    r = subprocess.run([node, "--check", path], capture_output=True, text=True)
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
