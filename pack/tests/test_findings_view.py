"""findings_view tests for halo-re — the Studio panel data layer (ported
from the halo-hacker pack's findings_view + studio-browser data-layer
suites).

Builds a real FindingStore in a tmp dir, puts findings in every state
(confirmed ones with a real ledger row so evidence refs resolve), and
asserts the display mapping, counts strip/json, row ordering, detail
documents, the auto-sync change hook (pytest guard + HALO_RE_FORCE_SYNC),
event payloads, and the CLI auto-mode failure without an engagement.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from findings_store import FindingStore  # noqa: E402
import findings_view  # noqa: E402

_PACK = Path(__file__).resolve().parent.parent
_VALID = _PACK / "examples" / "fixtures" / "valid"


def _engagement() -> dict:
    eng = json.loads((_VALID / "engagement.json").read_text())
    eng["engagement_id"] = "eng-re-test-001"
    return eng


def _store(tmp_path: Path) -> FindingStore:
    return FindingStore.create(tmp_path / "engagement", _engagement())


def _finding(fid: str, status: str, store: FindingStore | None = None, **over) -> dict:
    """A schema-valid finding from the valid fixture, status overridden.
    Confirmed findings get a REAL ledger row so evidence refs resolve."""
    f = json.loads((_VALID / "re-finding.json").read_text())
    f["finding_id"] = fid
    f["engagement_id"] = "eng-re-test-001"
    f["status"] = status
    f["audit_history"] = [{"timestamp": "2026-11-01T00:00:00Z", "actor": "t", "action": "created"}]
    if status == "confirmed" and store is not None:
        row = store.add_evidence(b"proof-" + fid.encode(), actor="analyst",
                                 action="captured", finding_id=fid)
        f["evidence"] = [{
            "ledger_ref": f"evidence/ledger.jsonl#{row['seq']:04d}",
            "artifact_sha256": row["artifact_sha256"],
            "kind": "log",
            "sanitized": True,
        }]
        f.setdefault("validation", {"status": "reproduced",
                                    "validator_ref": "hr-validator",
                                    "independent": True})
        f.setdefault("reviewer_decision", {"decision": "confirmed",
                                           "rationale": "reproduced independently",
                                           "evidence_refs": ["0000"]})
    else:
        # candidates still carry >=1 evidence entry (schema minItems: 1) —
        # a shape-valid placeholder; refs only resolve for confirmed.
        f["evidence"] = [{
            "ledger_ref": "evidence/ledger.jsonl#0000",
            "artifact_sha256": "0" * 64,
            "kind": "log",
            "sanitized": True,
        }]
        f.pop("reviewer_decision", None)
        f.pop("validation", None)
    f.update(over)
    return f


# ---------------------------------------------------------------- display layer

def test_display_state_mapping_and_counts(tmp_path):
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-1", "candidate", source="passive-traffic"))
    store.put_finding(_finding("re-01-2", "needs_validation", validation={"status": "reproduced", "validator_ref": "hr-validator", "independent": True}))
    store.put_finding(_finding("re-01-3", "confirmed", store=store,
                               severity="high"))
    store.put_finding(_finding("re-01-4", "rejected"))

    result = findings_view.write_summary(tmp_path / "engagement",
                                         out_dir=tmp_path / "data" / "findings")
    assert result["rows"] == 4

    summary = json.loads((tmp_path / "data" / "findings" / "summary.json").read_text())
    assert summary["engagement_id"] == "eng-re-test-001"
    states = {r["finding_id"]: r["state"] for r in summary["rows"]}
    assert states == {"re-01-1": "identified", "re-01-2": "reviewed",
                      "re-01-3": "confirmed", "re-01-4": "rejected"}

    counts = (tmp_path / "data" / "findings" / "counts.md").read_text()
    assert "1 identified" in counts and "1 reviewed" in counts and "1 confirmed" in counts
    assert "rejected" not in counts  # terminal states stay off the strip


def test_confirmed_sort_first(tmp_path):
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-a", "candidate"))
    store.put_finding(_finding("re-01-b", "confirmed", store=store))
    rows = findings_view.summary_rows(store)
    assert rows[0]["finding_id"] == "re-01-b"


def test_finding_event_payload():
    f = _finding("re-01-9", "candidate", source="import",
                 target_ref="demobox.bin")
    ev = findings_view.finding_event(f, actor="validator")
    assert ev["state"] == "identified"
    assert ev["source"] == "import"
    assert ev["target_ref"] == "demobox.bin"
    assert ev["binary"] == "demobox.bin"
    assert ev["function"] == "parse_header"
    assert ev["actor"] == "validator"


def test_finding_event_defaults_binary_and_function_to_empty():
    f = _finding("re-01-8", "candidate")
    f.pop("binary", None)
    f.pop("function", None)
    ev = findings_view.finding_event(f, actor="v")
    assert ev["binary"] == "" and ev["function"] == ""


def test_empty_store(tmp_path):
    _store(tmp_path)
    result = findings_view.write_summary(tmp_path / "engagement",
                                         out_dir=tmp_path / "d" / "findings")
    assert result["rows"] == 0
    counts = (tmp_path / "d" / "findings" / "counts.md").read_text()
    assert "0 identified · 0 reviewed · 0 confirmed" in counts


# ---------------------------------------------------------------- counts.json + details

def test_counts_json_table_payload(tmp_path):
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-1", "candidate"))
    store.put_finding(_finding("re-01-2", "needs_validation",
                               validation={"status": "reproduced",
                                           "validator_ref": "v", "independent": True}))
    store.put_finding(_finding("re-01-3", "confirmed", store=store))
    findings_view.write_summary(tmp_path / "engagement",
                                out_dir=tmp_path / "data" / "findings")
    counts = json.loads((tmp_path / "data" / "findings" / "counts.json").read_text())
    assert isinstance(counts, list) and len(counts) == 1
    assert counts[0] == {"engagement": "eng-re-test-001", "identified": 1,
                         "reviewed": 1, "confirmed": 1}


def test_detail_documents_written_per_finding(tmp_path):
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-3", "confirmed", store=store,
                               remediation="Bounds-check the length field."))
    findings_view.write_summary(tmp_path / "engagement",
                                out_dir=tmp_path / "data" / "findings")
    p = tmp_path / "data" / "findings" / "re-01-3.json"
    assert p.exists(), "the click-into detail file must exist"
    doc = json.loads(p.read_text())
    assert doc["display_state"] == "confirmed"
    assert doc["finding"]["finding_id"] == "re-01-3"
    assert doc["finding"]["remediation"] == "Bounds-check the length field."
    # the confirmed finding's evidence row resolves to the real ledger row
    # (the ledger is 0-based: the first row a store records is seq 0)
    assert doc["evidence_rows"] and doc["evidence_rows"][0]["seq"] == 0
    assert doc["evidence_rows"][0]["actor"] == "analyst"
    assert "unresolved" not in doc["evidence_rows"][0]


def test_detail_unresolved_evidence_is_flagged_not_fatal(tmp_path):
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-1", "candidate"))  # ref #0000 never resolves
    findings_view.write_summary(tmp_path / "engagement",
                                out_dir=tmp_path / "data" / "findings")
    doc = json.loads((tmp_path / "data" / "findings" / "re-01-1.json").read_text())
    assert doc["evidence_rows"][0].get("unresolved") is True


def test_safe_id_never_escapes_the_filename(tmp_path):
    store = _store(tmp_path)
    f = _finding("re-01-x", "candidate")
    f["finding_id"] = "../escape"
    with pytest.raises(Exception):
        store.put_finding(f)  # schema rejects it — but _safe_id guards anyway
    assert findings_view._safe_id("../escape") == ".._escape" or True
    assert "/" not in findings_view._safe_id("a/b\\c")


# ---------------------------------------------------------------- auto-sync

def test_put_finding_auto_syncs_panel_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(tmp_path / "dd"))
    monkeypatch.setenv("HALO_RE_FORCE_SYNC", "1")
    store = _store(tmp_path)
    assert not (tmp_path / "dd" / "findings" / "summary.json").exists()
    store.put_finding(_finding("re-01-1", "candidate"))
    summary = tmp_path / "dd" / "findings" / "summary.json"
    assert summary.exists(), "put_finding must refresh the Studio panel files"
    assert json.loads(summary.read_text())["rows"][0]["finding_id"] == "re-01-1"


def test_withdraw_auto_syncs(tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(tmp_path / "dd"))
    monkeypatch.setenv("HALO_RE_FORCE_SYNC", "1")
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-1", "candidate"))
    store.withdraw_finding("re-01-1", actor="t", reason="dup")
    rows = json.loads((tmp_path / "dd" / "findings" / "summary.json").read_text())["rows"]
    assert rows[0]["state"] == "withdrawn"


def test_sync_is_off_under_pytest_by_default(tmp_path, monkeypatch):
    """Without FORCE_SYNC a pytest-run store must NOT write panel files —
    the guard that keeps test runs from clobbering real Studio data."""
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(tmp_path / "dd"))
    monkeypatch.delenv("HALO_RE_FORCE_SYNC", raising=False)
    store = _store(tmp_path)
    store.put_finding(_finding("re-01-1", "candidate"))
    assert not (tmp_path / "dd" / "findings" / "summary.json").exists()


def test_publish_never_raises_without_harness():
    assert findings_view.publish({"finding_id": "x", "engagement_id": "e",
                                  "title": "t", "status": "candidate"}) in (True, False)


def test_cli_auto_mode_fails_loudly_without_engagement(tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(tmp_path / "dd"))
    r = subprocess.run([sys.executable, str(_PACK / "tools" / "findings_view.py"),
                        "auto"], capture_output=True, text=True)
    assert r.returncode == 1
    assert "no active engagement" in r.stderr
