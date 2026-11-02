#!/usr/bin/env python3
"""Halo RE findings store — the engagement-tree runtime.

Implements the engagement-tree design (ported from the halo-hacker pack,
battle-tested structure kept intact):

    <state>/engagements/<eng-id>/
      engagement.json        scope + authorization (schema-validated)
      evidence/
        ledger.jsonl         append-only, HASH-CHAINED, atomic appends
        artifacts/<sha256>/  content-addressed blobs
        checkpoints/         durable chain heads (copy one off-box)
      findings/<finding-id>/finding.json
      report/report.md       GENERATED, never hand-written

Hard rules, mechanically enforced (P0 hardening carried over from the
2026-10-21 external review — all findings addressed in the source port):
- FAIL CLOSED: jsonschema is a hard dependency. No validation, no store.
- NO DELETE for audit records; controlled WITHDRAWAL/PURGE exists for
  sensitive content (a tombstone + audit entry replaces removal, and
  purged artifacts leave a recorded marker — the audit survives).
- A 'confirmed' finding must satisfy the schema's conditional (independent
  reproduced validation + judge decision) AND its evidence references
  must RESOLVE against the actual ledger rows.
- Authorization is checked at write time: window and status. An expired
  or non-active engagement refuses evidence and findings.
- Chain tampering, row removal (below a checkpoint), and artifact
  corruption are each detectable; checkpoints are the external anchor.
- All writes are atomic (temp file + os.replace) — a crash never leaves
  a partial ledger row or finding record.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import jsonschema  # MANDATORY — fail closed, no degraded mode

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_ENGAGEMENT_SCHEMA = json.loads((_SCHEMA_DIR / "re-engagement.schema.json").read_text())
_FINDING_SCHEMA = json.loads((_SCHEMA_DIR / "re-finding.schema.json").read_text())


class FindingStoreError(Exception):
    """Refusals are the store working, not failing."""


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _parse_window_ts(ts: str) -> float:
    # ISO-8601 (Z-suffixed in our fixtures); tolerant parse, never guesses.
    from datetime import datetime, timezone
    t = str(ts).replace("Z", "+00:00")
    return datetime.fromisoformat(t).timestamp() if t else 0.0


class FindingStore:
    def __init__(self, engagement_root: Path):
        self.root = Path(engagement_root)
        self.evidence = self.root / "evidence"
        self.ledger = self.evidence / "ledger.jsonl"
        self.artifacts = self.evidence / "artifacts"
        self.checkpoints = self.evidence / "checkpoints"
        self.findings_dir = self.root / "findings"
        self.report_dir = self.root / "report"
        # Studio sync (findings_view.attach): every mutation rewrites the
        # pack's panel files and publishes a re.finding event. Best-effort
        # only — a view failure must never fail the store.
        self.change_hooks: list = []
        try:
            from findings_view import attach as _attach_view
            _attach_view(self)
        except Exception:
            pass

    def _changed(self, finding: dict) -> None:
        """Notify change hooks (Studio sync). Never raises."""
        for hook in list(self.change_hooks):
            try:
                hook(finding)
            except Exception:
                pass

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, engagement_root: Path, engagement: dict) -> "FindingStore":
        """Create the engagement tree. The engagement record MUST pass
        re-engagement.schema.json — no engagement object without a valid,
        signed-scope-shaped record."""
        root = Path(engagement_root)
        if (root / "engagement.json").exists():
            raise FindingStoreError(f"engagement already exists at {root}")
        jsonschema.validate(engagement, _ENGAGEMENT_SCHEMA)
        for d in (root, root / "evidence" / "artifacts",
                  root / "evidence" / "checkpoints", root / "findings",
                  root / "report", root / "context"):
            d.mkdir(parents=True, exist_ok=True)
        _atomic_write(root / "engagement.json", json.dumps(engagement, indent=2))
        return cls(root)

    def engagement(self) -> dict:
        return json.loads((self.root / "engagement.json").read_text())

    # -- authorization (checked at write time; fail closed) -----------------

    def check_authorization(self) -> None:
        """Refuse writes outside the authorization window or when the
        engagement is not active. The store itself refuses to record work
        done without authorization."""
        eng = self.engagement()
        status = eng.get("status", "active")
        if status != "active":
            raise FindingStoreError(
                f"engagement status is {status!r}; refusing to record — "
                "only an active engagement accepts evidence and findings")
        now = time.time()
        start = _parse_window_ts(eng["window"]["start"])
        expires = _parse_window_ts(eng["window"]["expires"])
        if now < start:
            raise FindingStoreError(
                f"engagement window opens {eng['window']['start']}; too early")
        if now > expires:
            raise FindingStoreError(
                f"engagement window expired {eng['window']['expires']}; refusing")

    # -- evidence (hash-chained ledger + content-addressed artifacts) ------

    def add_evidence(self, content: bytes, *, actor: str, action: str,
                     finding_id: Optional[str] = None,
                     meta: Optional[dict] = None) -> dict:
        """Store an artifact (content-addressed) and append a chained row.
        Identical content dedupes naturally (same sha256 dir)."""
        self.check_authorization()
        sha = _sha256(content)
        art_dir = self.artifacts / sha
        if not art_dir.exists():
            art_dir.mkdir(parents=True)
            (art_dir / "artifact.bin").write_bytes(content)
        rows = self._read_rows()
        prev = rows[-1]["hash"] if rows else "0" * 64
        row = {
            "seq": len(rows),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor,
            "action": action,
            "artifact_sha256": sha,
            "finding_id": finding_id,
            "meta": meta or {},
            "prev_hash": prev,
        }
        row["hash"] = _sha256(_canonical(row).encode())
        # Atomic append: temp + replace, so a crash never writes half a row.
        fd, tmp = tempfile.mkstemp(dir=str(self.evidence), prefix=".ledger-")
        with os.fdopen(fd, "w") as f:
            if self.ledger.exists():
                f.write(self.ledger.read_text())
            f.write(json.dumps(row) + "\n")
        os.replace(tmp, self.ledger)
        return row

    def _read_rows(self) -> list:
        if not self.ledger.exists():
            return []
        return [json.loads(line) for line in
                self.ledger.read_text().splitlines() if line.strip()]

    def resolve_ledger_ref(self, ref: str) -> dict:
        """Resolve an evidence ledger reference ('...#NNNN' or plain row
        number) to the actual row. Unresolvable references are refusals,
        not warnings."""
        seq = int(ref.rsplit("#", 1)[-1]) if "#" in ref else None
        for row in self._read_rows():
            if (seq is not None and row["seq"] == seq) or ref == row["hash"]:
                return row
        raise FindingStoreError(f"evidence reference does not resolve in the ledger: {ref!r}")

    def verify_chain(self) -> list[str]:
        """Re-walk the ledger. Returns an empty list if intact; one plain
        line per problem otherwise (tampering/removal is detectable)."""
        problems: list[str] = []
        rows = self._read_rows()
        prev = "0" * 64
        for expect_seq, row in enumerate(rows):
            if row.get("seq") != expect_seq:
                problems.append(f"row {expect_seq}: bad seq {row.get('seq')}")
            if row.get("prev_hash") != prev:
                problems.append(f"row {expect_seq}: prev_hash mismatch "
                                f"(chain broken or a row was removed)")
            claimed = row.get("hash")
            body = {k: v for k, v in row.items() if k != "hash"}
            if _sha256(_canonical(body).encode()) != claimed:
                problems.append(f"row {expect_seq}: hash mismatch (row tampered)")
            prev = claimed
            sha = row.get("artifact_sha256")
            if sha:
                p = self.artifacts / str(sha) / "artifact.bin"
                if (self.artifacts / str(sha) / "PURGED").exists():
                    continue  # recorded purge: the audit row survives by design
                if not p.exists():
                    problems.append(f"row {expect_seq}: artifact {sha[:12]}… missing")
                elif _sha256(p.read_bytes()) != sha:
                    problems.append(f"row {expect_seq}: artifact {sha[:12]}… hash mismatch")
        # Truncation below any checkpoint is detectable: a checkpoint is an
        # external anchor (copy it off-box); the ledger can never honestly
        # be shorter than a checkpoint that was taken.
        for cp in sorted(self.checkpoints.glob("checkpoint-*.json")) if self.checkpoints.exists() else []:
            c = json.loads(cp.read_text())
            if len(rows) < c["count"]:
                problems.append(
                    f"{cp.name}: ledger has {len(rows)} rows but checkpoint "
                    f"recorded {c['count']} — rows were removed after the checkpoint")
            elif len(rows) >= c["count"] and rows[c["count"] - 1]["hash"] != c["head"]:
                problems.append(f"{cp.name}: head mismatch at row {c['count'] - 1}")
        return problems

    def checkpoint(self, label: str = "") -> dict:
        """Take a durable checkpoint of the chain head. The returned dict is
        meant to be copied OUTSIDE the engagement tree (that's what makes
        truncation detectable against someone with filesystem write access);
        a copy is also kept under evidence/checkpoints/."""
        rows = self._read_rows()
        cp = {
            "count": len(rows),
            "head": rows[-1]["hash"] if rows else "0" * 64,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": label,
        }
        name = time.strftime("checkpoint-%Y%m%dT%H%M%SZ", time.gmtime())
        _atomic_write(self.checkpoints / f"{name}.json", json.dumps(cp, indent=2))
        return cp

    def verify_against_checkpoint(self, count: int, head: str) -> list[str]:
        """Verify the ledger against an EXTERNALLY stored checkpoint dict.
        This is the strong guarantee: a local rewrite cannot forge the
        off-box head."""
        rows = self._read_rows()
        if len(rows) < count:
            return [f"ledger truncated: {len(rows)} rows < checkpoint's {count}"]
        if rows[count - 1]["hash"] != head:
            return [f"chain head at row {count - 1} does not match the checkpoint"]
        return []

    def evidence_rows(self, finding_id: Optional[str] = None) -> list:
        rows = self._read_rows()
        return [r for r in rows if finding_id is None or r.get("finding_id") == finding_id]

    # -- findings (gated, no delete; controlled withdrawal) -----------------

    def put_finding(self, finding: dict) -> Path:
        """Insert or update a finding. MUST pass re-finding.schema.json
        (incl. the confirmed-conditional) AND, when confirmed, every
        evidence reference must resolve to a real ledger row whose artifact
        hash matches."""
        self.check_authorization()
        jsonschema.validate(finding, _FINDING_SCHEMA)
        if finding.get("status") == "confirmed":
            self._resolve_evidence_refs(finding)
        d = self.findings_dir / finding["finding_id"]
        d.mkdir(parents=True, exist_ok=True)
        _atomic_write(d / "finding.json", json.dumps(finding, indent=2))
        self._changed(finding)
        return d / "finding.json"

    def _resolve_evidence_refs(self, finding: dict) -> None:
        for ev in finding.get("evidence", []):
            try:
                row = self.resolve_ledger_ref(ev["ledger_ref"])
            except FindingStoreError as e:
                raise FindingStoreError(
                    f"confirmed finding {finding['finding_id']}: {e}") from e
            sha = ev.get("artifact_sha256")
            if sha and sha != row["artifact_sha256"]:
                raise FindingStoreError(
                    f"confirmed finding {finding['finding_id']}: evidence "
                    f"{ev['ledger_ref']!r} names artifact {sha[:12]}… but the "
                    f"ledger row holds {row['artifact_sha256'][:12]}…")

    def get_finding(self, finding_id: str) -> dict:
        p = self.findings_dir / finding_id / "finding.json"
        if not p.exists():
            raise FindingStoreError(f"no such finding: {finding_id}")
        return json.loads(p.read_text())

    def list_findings(self, status: Optional[str] = None) -> list[dict]:
        out = []
        if not self.findings_dir.exists():
            return out
        for p in sorted(self.findings_dir.glob("*/finding.json")):
            f = json.loads(p.read_text())
            if status is None or f.get("status") == status:
                out.append(f)
        return out

    def mark_duplicate(self, finding_id: str, duplicate_of: str, actor: str) -> dict:
        """Judge operation: mark a finding as a duplicate of another,
        recording the audit entry. Refuses self-duplicates."""
        if finding_id == duplicate_of:
            raise FindingStoreError("a finding cannot duplicate itself")
        f = self.get_finding(finding_id)
        self.get_finding(duplicate_of)  # must exist
        f["status"] = "duplicate"
        f["duplicate_of"] = duplicate_of
        f.setdefault("audit_history", []).append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor, "action": "marked-duplicate",
            "detail": f"duplicate of {duplicate_of}"})
        self.put_finding(f)
        return f

    def withdraw_finding(self, finding_id: str, actor: str, reason: str) -> dict:
        """CONTROLLED withdrawal (client artifacts and personal data need
        controlled retention and deletion). Replaces the record content
        with a tombstone that keeps the id, the audit history, and the
        ORIGINAL RECORD'S HASH — the sensitive content is gone, the audit
        trail of its existence survives. Refuses to withdraw an
        already-withdrawn record."""
        f = self.get_finding(finding_id)
        if f.get("status") == "withdrawn":
            raise FindingStoreError(f"{finding_id} is already withdrawn")
        original_hash = _sha256(json.dumps(f, sort_keys=True).encode())
        tombstone = {
            "finding_id": finding_id,
            "engagement_id": f.get("engagement_id"),
            "title": "[WITHDRAWN]",
            "category": f.get("category", "n/a"),
            "description": f"Withdrawn by {actor}: {reason}. "
                           "Content removed; audit record preserved. "
                           f"Original record sha256: {original_hash}",
            "evidence": f.get("evidence", []),  # refs survive; artifacts can be purged
            "status": "withdrawn",
            "audit_history": f.get("audit_history", []) + [{
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "actor": actor, "action": "withdrawn",
                "detail": f"reason: {reason}; original sha256 {original_hash}"}],
        }
        _atomic_write(self.findings_dir / finding_id / "finding.json",
                      json.dumps(tombstone, indent=2))
        self._changed(tombstone)
        return tombstone

    def purge_artifact(self, artifact_sha256: str, actor: str, reason: str) -> None:
        """Remove an artifact's BYTES while keeping the ledger row and a
        recorded PURGED marker — deletion with an audit record, not a
        silent disappearance. The chain stays verifiable."""
        d = self.artifacts / artifact_sha256
        if not d.exists():
            raise FindingStoreError(f"no such artifact: {artifact_sha256[:12]}…")
        (d / "artifact.bin").unlink(missing_ok=True)
        _atomic_write(d / "PURGED", json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor, "reason": reason,
            "artifact_sha256": artifact_sha256,
        }, indent=2))

    # -- the rule that has no method --------------------------------------

    def delete_finding(self, *args, **kwargs):  # pragma: no cover
        raise FindingStoreError(
            "no delete verb, ever — use withdraw_finding() for controlled "
            "removal with an audit record, or edit as a human")
