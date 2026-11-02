"""Studio contribution tests — the findings browser bundle panel.

Covers the manifest declaration (bundle panel, studio-script grant,
palette routes, config_form, the counts TABLE reading the data folder)
and the browser module's CSP hygiene (no innerHTML, no inline styles, no
external resources) plus a node syntax check when node exists.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

_PACK = Path(__file__).resolve().parent.parent
_JS = _PACK / "studio" / "findings.js"


def _manifest() -> dict:
    try:
        import yaml
    except ImportError:
        pytest.skip("SKIPPED -- pyyaml not installed")
    return yaml.safe_load((_PACK / "pack.yaml").read_text())


def test_manifest_declares_the_bundle_panel():
    m = _manifest()
    studio = m["contributes"]["studio"]
    section = studio["sections"][0]
    panels = {p["id"]: p for p in section["panels"]}
    assert panels["browser"]["kind"] == "bundle"
    assert panels["browser"]["source"] == "studio/findings.js"
    assert (_PACK / "studio" / "findings.js").exists()
    # the counts panel is a TABLE reading the data folder (markdown cannot)
    assert panels["counts"]["kind"] == "table"
    assert panels["counts"]["source"] == "data:findings/counts.json"
    assert "studio-script" in m["permissions"]


def test_manifest_palette_routes_resolve():
    m = _manifest()
    studio = m["contributes"]["studio"]
    section = studio["sections"][0]
    panel_ids = {p["id"] for p in section["panels"]}
    for line in studio.get("palette", []):
        action = line["action"]
        assert action.startswith("route:")
        target = action[len("route:"):]
        assert target.split("/")[0] == section["id"]
        if "/" in target:
            assert target.split("/")[1] in panel_ids, f"palette route to nothing: {action}"
    assert studio.get("config_form") is True


def test_browser_js_targets_this_pack():
    js = _JS.read_text()
    assert "api/pack/halo-re/data/findings/summary.json" in js
    assert "halo-hacker" not in js, "the browser must not point at the sibling pack"


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
