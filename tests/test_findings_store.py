"""Findings store tests for halo-re (ported from the halo-hacker pack's
store suite): create/put/authorization/withdraw/purge/chain/checkpoint,
plus report generation from confirmed findings only. All offline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK_ROOT / "tools"))

from findings_store import FindingStore, FindingStoreError  # noqa: E402
import report as report_mod  # noqa: E402

FIXTURES = PACK_ROOT / "examples" / "fixtures" / "valid"


def seed_confirmed(store, finding):
    """Give a confirmed finding resolvable evidence (a real ledger row)."""
    row = store.add_evidence(
        ("evidence for " + finding["finding_id"]).encode(),
        actor="hr-validator", action="capture")
    finding["evidence"][0]["ledger_ref"] = f"eng/evidence/ledger.jsonl#{row['seq']}"
    finding["evidence"][0]["artifact_sha256"] = row["artifact_sha256"]
    return finding

jsonschema = pytest.importorskip(
    "jsonschema", reason="SKIPPED -- jsonschema not installed "
    "(uv run --with jsonschema to exercise store + schema validation)")


@pytest.fixture()
def store(tmp_path):
    eng = json.loads((FIXTURES / "engagement.json").read_text())
    return FindingStore.create(tmp_path / "eng", eng)


# --- findings store ----------------------------------------------------------

def test_create_requires_valid_engagement(tmp_path):
    bad = json.loads((FIXTURES / "engagement.json").read_text())
    bad["allowed_activities"] = ["disruptive-testing"]  # not an RE activity
    with pytest.raises(jsonschema.ValidationError):
        FindingStore.create(tmp_path / "bad", bad)


def test_evidence_chain_and_dedupe(store):
    r1 = store.add_evidence(b"POST /parse header blob ...", actor="hr-validator",
                            action="capture", finding_id="re-01-heap-overflow")
    r2 = store.add_evidence(b"POST /parse header blob ...", actor="hr-validator",
                            action="capture", finding_id="re-01-heap-overflow")
    assert r1["artifact_sha256"] == r2["artifact_sha256"]  # content dedupe
    assert r2["prev_hash"] == r1["hash"]
    assert store.verify_chain() == []
    assert len(store.evidence_rows()) == 2


def test_chain_tamper_detected(store):
    store.add_evidence(b"a", actor="x", action="y")
    store.add_evidence(b"b", actor="x", action="y")
    # Tamper with row 0's content.
    rows = store.ledger.read_text().splitlines()
    row = json.loads(rows[0])
    row["action"] = "never-happened"
    rows[0] = json.dumps(row)
    store.ledger.write_text("\n".join(rows) + "\n")
    problems = store.verify_chain()
    assert any("row 0" in p for x in [problems] for p in x), problems


def test_row_removal_detected(store):
    store.add_evidence(b"a", actor="x", action="y")
    store.add_evidence(b"b", actor="x", action="y")
    store.add_evidence(b"c", actor="x", action="y")
    lines = store.ledger.read_text().splitlines()
    del lines[1]  # remove the middle row
    store.ledger.write_text("\n".join(lines) + "\n")
    assert store.verify_chain() != []


def test_artifact_corruption_detected(store):
    sha_row = store.add_evidence(b"original", actor="x", action="y")
    p = store.artifacts / sha_row["artifact_sha256"] / "artifact.bin"
    p.write_bytes(b"tampered")
    problems = store.verify_chain()
    assert any("hash mismatch" in x for x in problems)


def test_finding_must_pass_schema(store):
    bad = json.loads((PACK_ROOT / "examples/fixtures/invalid"
                      / "re-finding-asserted-confirmed.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        store.put_finding(bad)


def test_finding_roundtrip_and_no_delete(store):
    f = seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text()))
    f["status"] = "confirmed"
    f["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                       "independent": True}
    f["reviewer_decision"] = {"decision": "confirmed", "rationale": "reproduced",
                              "evidence_refs": ["0000"]}
    store.put_finding(f)
    assert store.get_finding(f["finding_id"])["status"] == "confirmed"
    with pytest.raises(FindingStoreError):
        store.delete_finding(f["finding_id"])


def test_duplicate_marking(store):
    store.put_finding(seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text())))
    f = seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text()))
    f["finding_id"] = "re-02-second-instance"
    f["title"] = "Second instance of the same overflow"
    store.put_finding(f)
    out = store.mark_duplicate("re-02-second-instance",
                               "re-01-heap-overflow", actor="hr-judge")
    assert out["status"] == "duplicate"
    assert out["duplicate_of"] == "re-01-heap-overflow"
    with pytest.raises(FindingStoreError):
        store.mark_duplicate("re-02-second-instance", "re-02-second-instance",
                             actor="hr-judge")


def test_findings_persist_across_instances(store, tmp_path):
    store.put_finding(seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text())))
    # A NEW store over the same tree sees it — persistence across
    # sessions and model changes.
    assert FindingStore(tmp_path / "eng").list_findings()


# --- report generation -------------------------------------------------------

def test_report_from_confirmed_only(store):
    confirmed = seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text()))
    confirmed["status"] = "confirmed"
    confirmed["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                               "independent": True}
    confirmed["reviewer_decision"] = {
        "decision": "confirmed",
        "rationale": "Reproduced independently from the record.",
        "confidence": "high",
        "severity_rationale": "Attacker-controlled overflow in a parser.",
        "evidence_refs": ["0000"]}
    store.put_finding(confirmed)
    cand = json.loads((FIXTURES / "re-finding.json").read_text())
    cand["finding_id"] = "re-03-unvalidated"
    cand["status"] = "candidate"
    store.put_finding(cand)
    out = report_mod.generate_report(store)
    text = out.read_text()
    assert "re-01-heap-overflow" in text                # confirmed: detailed
    assert "### re-03-unvalidated" not in text          # candidate: NOT detailed
    assert "re-03-unvalidated | candidate" in text      # but listed in coverage
    assert "ledger row" in text                         # evidence trace present
    assert out == store.report_dir / "report.md"


def test_report_shows_binary_function_cwe(store):
    confirmed = seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text()))
    confirmed["status"] = "confirmed"
    confirmed["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                               "independent": True}
    confirmed["reviewer_decision"] = {"decision": "confirmed",
                                      "rationale": "reproduced",
                                      "evidence_refs": ["0000"]}
    store.put_finding(confirmed)
    text = report_mod.generate_report(store).read_text()
    assert "**Binary:** demobox.bin" in text
    assert "**Function:** parse_header (CWE: CWE-122)" in text


def test_report_refuses_broken_chain(store):
    store.put_finding(seed_confirmed(store, json.loads((FIXTURES / "re-finding.json").read_text())))
    store.add_evidence(b"x", actor="a", action="b")
    p = store.ledger
    lines = p.read_text().splitlines()
    row = json.loads(lines[0]); row["actor"] = "evil"; lines[0] = json.dumps(row)
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(report_mod.ReportError):
        report_mod.generate_report(store)


# --- P0 hardening (carried over from the source pack's external review) -------

def test_confirmed_requires_independent_validation_schema():
    # Non-empty evidence, but no validation/reviewer_decision: the schema's
    # allOf conditional must reject it.
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["status"] = "confirmed"
    schema = json.loads((PACK_ROOT / "schemas" / "re-finding.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(f, schema)


def test_confirmed_with_nonindependent_validation_rejected():
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["status"] = "confirmed"
    f["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                       "independent": False}   # shared the analyst's session
    f["reviewer_decision"] = {"decision": "confirmed", "rationale": "r",
                              "evidence_refs": ["0000"]}
    schema = json.loads((PACK_ROOT / "schemas" / "re-finding.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(f, schema)


def test_cwe_pattern_enforced():
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["cwe"] = "CWE 122"  # not the ^CWE-[0-9]+$ shape
    schema = json.loads((PACK_ROOT / "schemas" / "re-finding.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(f, schema)


def test_store_resolves_confirmed_evidence_refs(store):
    # A confirmed finding whose ledger_ref does NOT resolve is refused by
    # the store even though the schema passed.
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["status"] = "confirmed"
    f["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                       "independent": True}
    f["reviewer_decision"] = {"decision": "confirmed", "rationale": "r",
                              "evidence_refs": ["0000"]}
    f["evidence"][0]["ledger_ref"] = "nowhere#9999"
    with pytest.raises((FindingStoreError,)):
        store.put_finding(f)


def test_store_accepts_confirmed_with_resolved_refs(store):
    row = store.add_evidence(b"parse_header trace: copy pastes bounds",
                             actor="hr-validator", action="capture")
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["status"] = "confirmed"
    f["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                       "independent": True}
    f["reviewer_decision"] = {"decision": "confirmed", "rationale": "r",
                              "evidence_refs": ["0000"]}
    f["evidence"][0]["ledger_ref"] = f"eng/evidence/ledger.jsonl#{row['seq']}"
    f["evidence"][0]["artifact_sha256"] = row["artifact_sha256"]
    store.put_finding(f)
    assert store.get_finding(f["finding_id"])["status"] == "confirmed"


def test_store_refuses_mismatched_artifact_hash(store):
    row = store.add_evidence(b"real evidence", actor="a", action="b")
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    f["status"] = "confirmed"
    f["validation"] = {"status": "reproduced", "validator_ref": "hr-validator",
                       "independent": True}
    f["reviewer_decision"] = {"decision": "confirmed", "rationale": "r",
                              "evidence_refs": ["0000"]}
    f["evidence"][0]["ledger_ref"] = f"x#{row['seq']}"
    f["evidence"][0]["artifact_sha256"] = "f" * 64  # wrong hash
    with pytest.raises(FindingStoreError):
        store.put_finding(f)


def test_store_fails_closed_without_jsonschema(store):
    # jsonschema is a hard import; simulate absence by nulling it in the
    # module — create() must refuse, not degrade.
    import findings_store as fs
    real = fs.jsonschema
    fs.jsonschema = None
    try:
        with pytest.raises(Exception):
            fs.FindingStore.create(store.root.parent / "eng2",
                                   json.loads((FIXTURES / "engagement.json").read_text()))
    finally:
        fs.jsonschema = real


def test_authorization_window_enforced(tmp_path):
    eng = json.loads((FIXTURES / "engagement.json").read_text())
    eng["engagement_id"] = "expired-re-01"
    eng["window"] = {"start": "2020-01-01T00:00:00Z",
                     "expires": "2020-02-01T00:00:00Z"}
    st = FindingStore.create(tmp_path / "expired", eng)
    with pytest.raises(FindingStoreError, match="expired"):
        st.add_evidence(b"x", actor="a", action="b")


def test_authorization_status_enforced(tmp_path):
    eng = json.loads((FIXTURES / "engagement.json").read_text())
    eng["status"] = "paused"
    st = FindingStore.create(tmp_path / "paused", eng)
    with pytest.raises(FindingStoreError, match="paused"):
        st.put_finding(json.loads((FIXTURES / "re-finding.json").read_text()))


def test_checkpoint_detects_truncation(store):
    for i in range(3):
        store.add_evidence(f"evidence {i}".encode(), actor="a", action="b")
    cp = store.checkpoint(label="off-box copy")   # copy this dict off-box
    assert store.verify_against_checkpoint(cp["count"], cp["head"]) == []
    # Truncate the ledger locally (rewrite + recompute is possible with
    # filesystem access) — the EXTERNAL checkpoint still catches it.
    lines = store.ledger.read_text().splitlines()
    store.ledger.write_text("\n".join(lines[:2]) + "\n")
    assert store.verify_against_checkpoint(cp["count"], cp["head"]) != []
    # And the on-box checkpoint copy catches it too.
    assert any("checkpoint" in x for x in store.verify_chain())


def test_withdraw_preserves_audit_and_removes_content(store):
    f = json.loads((FIXTURES / "re-finding.json").read_text())
    store.put_finding(f)
    tomb = store.withdraw_finding("re-01-heap-overflow", actor="human",
                                  reason="proprietary constants in the record")
    assert tomb["status"] == "withdrawn"
    assert "Original record sha256:" in tomb["description"]
    got = store.get_finding("re-01-heap-overflow")
    assert got["title"] == "[WITHDRAWN]"
    assert got["description"].startswith("Withdrawn by human")
    with pytest.raises(FindingStoreError):
        store.withdraw_finding("re-01-heap-overflow", actor="h", reason="again")


def test_purge_artifact_keeps_chain_verifiable(store):
    row = store.add_evidence(b"sensitive artifact bytes", actor="a", action="b")
    assert store.verify_chain() == []
    store.purge_artifact(row["artifact_sha256"], actor="human",
                         reason="retention policy")
    # Bytes gone, marker present, chain still verifies (recorded purge).
    assert not (store.artifacts / row["artifact_sha256"] / "artifact.bin").exists()
    assert (store.artifacts / row["artifact_sha256"] / "PURGED").exists()
    assert store.verify_chain() == []
