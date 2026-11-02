"""Craft study tracker tests — the Craft & rebuild section's data layer.

A study round-trips through add/update/list into the pack DATA folder,
the panel files (studies.json, counts.json, per-study detail) carry the
shapes the Studio section reads, ids and statuses are validated, the
re.craft.study event payload validates against its schema, publish never
raises without the harness, and the CLI works end to end.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import craft_studies  # noqa: E402

_PACK = Path(__file__).resolve().parent.parent


@pytest.fixture()
def dd(tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(tmp_path / "dd"))
    return tmp_path / "dd"


def test_add_writes_panel_files(dd):
    craft_studies.add("cs-01-demo-app", "https://example.com/app", "web",
                      stack="react+vite", output="/tmp/rebuild", agent="claude",
                      notes="first pass")
    studies = json.loads((dd / "craft" / "studies.json").read_text())
    assert studies["rows"][0]["study_id"] == "cs-01-demo-app"
    assert studies["rows"][0]["status"] == "planned"
    assert studies["rows"][0]["mode"] == "clean-room"  # default mode
    counts = json.loads((dd / "craft" / "counts.json").read_text())
    assert counts == [{"studies": 1, "ready": 0, "in_progress": 1}]
    detail = json.loads((dd / "craft" / "cs-01-demo-app.json").read_text())
    assert detail["output"] == "/tmp/rebuild"
    assert detail["stack"] == "react+vite"


def test_update_status_and_check(dd):
    craft_studies.add("cs-01-demo-app", "https://example.com/app", "web")
    craft_studies.update("cs-01-demo-app", status="ready", mismatches=3,
                         check_note="layout at 1280px")
    row = craft_studies.get("cs-01-demo-app")
    assert row["status"] == "ready"
    assert row["check"] == {"mismatches": 3, "note": "layout at 1280px"}
    counts = json.loads((dd / "craft" / "counts.json").read_text())
    assert counts == [{"studies": 1, "ready": 1, "in_progress": 0}]


def test_bad_study_id_rejected(dd):
    with pytest.raises(ValueError):
        craft_studies.add("nope", "x", "web")
    with pytest.raises(ValueError):
        craft_studies.add("cs-1-CAPS", "x", "web")


def test_duplicate_and_unknown_rejected(dd):
    craft_studies.add("cs-01-demo-app", "x", "web")
    with pytest.raises(ValueError):
        craft_studies.add("cs-01-demo-app", "y", "app")
    with pytest.raises(ValueError):
        craft_studies.update("cs-99-missing", status="ready")


def test_bad_status_and_mode_rejected(dd):
    with pytest.raises(ValueError):
        craft_studies.add("cs-01-demo-app", "x", "web", mode="whatever")
    craft_studies.add("cs-01-demo-app", "x", "web")
    with pytest.raises(ValueError):
        craft_studies.update("cs-01-demo-app", status="almost-done")


def test_event_payload_validates_against_schema(dd):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("SKIPPED -- jsonschema not installed")
    craft_studies.add("cs-01-demo-app", "demobox.bin", "binary", mode="deep",
                      stack="rust", agent="codex")
    row = craft_studies.get("cs-01-demo-app")
    schema = json.loads((_PACK / "events" / "re.craft.study.json").read_text())
    payload = {"study_id": row["study_id"], "target": row["target"],
               "mode": row["mode"], "status": row["status"],
               "stack": row["stack"], "agent": row["agent"]}
    jsonschema.validate(payload, schema)


def test_publish_never_raises_without_harness(dd):
    assert craft_studies.publish({"study_id": "cs-01-x", "target": "t",
                                  "status": "planned"}) in (True, False)


def test_safe_id_never_escapes_the_filename():
    assert "/" not in craft_studies._safe_id("a/b\\c")
    assert craft_studies._safe_id("CS-01-X") == "cs-01-x"


def test_cli_add_then_list(tmp_path):
    r = subprocess.run([sys.executable, str(_PACK / "tools" / "craft_studies.py"),
                        "--data-dir", str(tmp_path / "cli"),
                        "add", "--id", "cs-01-cli", "--target", "https://x.test",
                        "--kind", "web", "--stack", "vue"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"] is True
    r = subprocess.run([sys.executable, str(_PACK / "tools" / "craft_studies.py"),
                        "--data-dir", str(tmp_path / "cli"), "list"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)[0]["study_id"] == "cs-01-cli"


def test_cli_error_is_fail_closed(tmp_path):
    r = subprocess.run([sys.executable, str(_PACK / "tools" / "craft_studies.py"),
                        "--data-dir", str(tmp_path / "cli"),
                        "update", "cs-99-missing", "--status", "ready"],
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "no such study" in r.stderr
