"""Reporting renderers tests for halo-re (ported from the halo-hacker
pack's suite).

Builds a real FindingStore in tmp_path, fabricates confirmed findings with real
ledger rows (so evidence refs resolve), and asserts the leadership email follows
the five-part shape and the full report follows the parallel template.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reporting"))

from findings_store import FindingStore  # noqa: E402
import leadership_email  # noqa: E402
import full_report  # noqa: E402

_VALID = Path(__file__).resolve().parent.parent / "examples" / "fixtures" / "valid"

BANNED_FUD = ("catastrophic", "nightmare", "doomed", "hackers are coming")
BULLET_STARTER_BLACKLIST = frozenset(
    ("the", "a", "an", "this", "it", "there", "that", "these", "those", "one", "some", "no")
)


def _engagement() -> dict:
    eng = json.loads((_VALID / "engagement.json").read_text())
    eng["engagement_id"] = "eng-re-test-001"
    return eng


def _store(tmp_path: Path) -> FindingStore:
    return FindingStore.create(tmp_path / "engagement", _engagement())


def _finding(fid: str, status: str, store: FindingStore | None = None, **over) -> dict:
    """A schema-valid finding from the valid fixture, status overridden.

    Confirmed findings get a REAL ledger row so evidence refs resolve.
    """
    f = json.loads((_VALID / "re-finding.json").read_text())
    f["finding_id"] = fid
    f["engagement_id"] = "eng-re-test-001"
    f["status"] = status
    f["audit_history"] = [
        {"timestamp": "2026-11-01T00:00:00Z", "actor": "t", "action": "created"}
    ]
    if status == "confirmed" and store is not None:
        row = store.add_evidence(
            b"proof-" + fid.encode(), actor="analyst", action="captured", finding_id=fid
        )
        f["evidence"] = [
            {
                "ledger_ref": f"evidence/ledger.jsonl#{row['seq']:04d}",
                "artifact_sha256": row["artifact_sha256"],
                "kind": "log",
                "sanitized": True,
            }
        ]
        f.setdefault("validation", {"status": "reproduced",
                                    "validator_ref": "hr-validator",
                                    "independent": True})
        f.setdefault("reviewer_decision", {"decision": "confirmed",
                                           "rationale": "reproduced independently",
                                           "evidence_refs": ["0000"]})
    else:
        f["evidence"] = [
            {
                "ledger_ref": "evidence/ledger.jsonl#0000",
                "artifact_sha256": "0" * 64,
                "kind": "log",
                "sanitized": True,
            }
        ]
        f.pop("reviewer_decision", None)
        f.pop("validation", None)
    f.update(over)
    return f


def _bullet_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip().startswith("- ")]


def _assert_no_fud(text: str) -> None:
    lowered = text.lower()
    for phrase in BANNED_FUD:
        assert phrase not in lowered, f"banned FUD phrase found: {phrase!r}"


def _assert_verb_first_bullets(text: str) -> None:
    for line in _bullet_lines(text):
        content = line.lstrip("- ").strip()
        match = re.match(r"^([A-Za-z]+)", content)
        assert match, f"bullet does not start with a word: {line!r}"
        first = match.group(1).lower()
        assert first not in BULLET_STARTER_BLACKLIST, (
            f"bullet appears to start with a non-verb: {line!r}"
        )


def test_leadership_email_renders_five_part_shape(tmp_path):
    store = _store(tmp_path)
    f1 = _finding(
        "re-01-overflow",
        "confirmed",
        store=store,
        severity="high",
        target_ref="demobox.bin",
        impact="Attacker-controlled memory corruption from a network-visible header.",
    )
    f2 = _finding(
        "re-02-pathtraverse",
        "confirmed",
        store=store,
        severity="medium",
        target_ref="demobox.bin",
        title="Path traversal in the update handler",
        impact="Arbitrary file read outside the intended data directory.",
    )
    store.put_finding(f1)
    store.put_finding(f2)

    email = leadership_email.render_leadership_email([f1, f2], store.engagement())
    assert set(email) == {"subject", "body", "mailto_url"}

    # Subject = takeaway: count + target + ask.
    assert "2 confirmed findings" in email["subject"]
    assert "demobox.bin" in email["subject"]
    assert " — " in email["subject"]

    # Body has exactly four blocks = five parts with subject.
    blocks = email["body"].strip().split("\n\n")
    assert len(blocks) == 4, f"expected 4 body blocks, got {len(blocks)}"

    _assert_no_fud(email["subject"])
    _assert_no_fud(email["body"])
    _assert_verb_first_bullets(email["body"])

    # mailto URL decodes back to the same subject and body.
    assert email["mailto_url"].startswith("mailto:?")
    query = email["mailto_url"].split("?", 1)[1]
    params = urllib.parse.parse_qs(query)
    assert urllib.parse.unquote(params["subject"][0]) == email["subject"]
    assert urllib.parse.unquote(params["body"][0]) == email["body"]


def test_leadership_email_rejects_candidate():
    f = _finding("re-01-candidate", "candidate")
    with pytest.raises(ValueError, match=r"re-01-candidate"):
        leadership_email.render_leadership_email([f], _engagement())


def test_leadership_email_rejects_empty():
    with pytest.raises(ValueError, match=r"no confirmed findings"):
        leadership_email.render_leadership_email([], _engagement())


def test_full_report_renders_parallel_template_and_appendix(tmp_path):
    store = _store(tmp_path)
    f1 = _finding(
        "re-01-overflow",
        "confirmed",
        store=store,
        severity="high",
        target_ref="demobox.bin",
        impact="Attacker-controlled memory corruption from a network-visible header.",
        remediation="Bounds-check the header length field before the copy loop.",
    )
    f2 = _finding(
        "re-02-pathtraverse",
        "confirmed",
        store=store,
        severity="medium",
        target_ref="demobox.bin",
        binary="updater.elf",
        function="apply_update",
        cwe="CWE-22",
        title="Path traversal in the update handler",
        impact="Arbitrary file read outside the intended data directory.",
        remediation="Normalize and confine update archive paths before extraction.",
    )
    store.put_finding(f1)
    store.put_finding(f2)

    report = full_report.render_full_report([f1, f2], store.engagement())
    assert set(report) == {"title", "markdown"}

    md = report["markdown"]

    # Title = strongest finding stated as impact.
    assert "Heap buffer overflow" in report["title"]
    assert "attacker-controlled memory corruption" in report["title"].lower()

    # Executive summary precedes the first finding section.
    exec_idx = md.index("## Executive summary")
    first_finding_idx = md.index("## Finding re-01-overflow")
    assert exec_idx < first_finding_idx

    # Headings are parallel: every finding section heading is a complete sentence.
    finding_headings = [h.lstrip("# ") for h in re.findall(r"^## Finding .+$", md, re.MULTILINE)]
    assert len(finding_headings) == 2
    for heading in finding_headings:
        assert heading.startswith("Finding ")
        assert heading.endswith(".")

    # Each finding points to the evidence appendix.
    assert md.count("See Appendix A for the complete evidence ledger references.") == 2

    # Appendix exists and lists ledger refs for every finding.
    assert "## Appendix A: Evidence ledger references" in md
    for f in (f1, f2):
        assert f"**{f['finding_id']}**" in md
        assert f["evidence"][0]["ledger_ref"] in md

    # RE localization shows when present, per finding block.
    assert "- Binary: demobox.bin" in md       # f1 inherits the fixture's binary
    assert "- Binary: updater.elf" in md       # f2 overrides it
    assert "- Function: apply_update (CWE: CWE-22)" in md

    _assert_no_fud(md)


def test_full_report_rejects_candidate():
    f = _finding("re-01-candidate", "candidate")
    with pytest.raises(ValueError, match=r"re-01-candidate"):
        full_report.render_full_report([f], _engagement())


def test_full_report_rejects_empty():
    with pytest.raises(ValueError, match=r"no confirmed findings"):
        full_report.render_full_report([], _engagement())
