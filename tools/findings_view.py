#!/usr/bin/env python3
"""Halo RE findings view — the data layer for the pack's Studio panels.

Reads a FindingStore (an engagement tree) and writes the files the Studio
panels declared in pack.yaml read from the pack's DATA folder:

- findings/summary.json — the findings table: one row per finding
  (finding_id, title, severity, state, target_ref, source, updated).
  Studio's table panel accepts {"rows": [...]} (or a bare array).
- findings/counts.json — one row {engagement, identified, reviewed,
  confirmed} for the counts TABLE panel (markdown panels cannot read the
  data folder; only table/artifact sources may use `data:`).
- findings/counts.md — the same counts as markdown, kept for direct
  reading and tests.
- findings/<finding_id>.json — the FULL finding document plus derived
  fields and its resolved evidence rows: what a Studio findings browser
  fetches when you click into a finding.

Display-state mapping: candidate→identified, validated→reviewed,
confirmed→confirmed; rejected/duplicate/withdrawn are terminal and
excluded from the strip but kept in the table rows.

Where the data folder is (in precedence order):
1. $HALO_RE_DATA_DIR (tests and headless runs)
2. halo_harness.ext.data_dir("halo-re") — the harness's own resolver,
   i.e. ~/.halo/packs/.data/halo-re/ (the folder Studio's `data:` panel
   sources are served from). Best-effort import: the pack never
   hard-depends on halo_harness.
3. ~/.halo/packs/.data/halo-re (the same place, by convention, when the
   harness import is unavailable).

Studio sync: attach(store) installs a change hook so every store
mutation (put_finding, withdraw, duplicate) rewrites the panel files and
publishes a re.finding event (halo_harness.ext.publish_event,
best-effort). FindingStore.__init__ attaches automatically unless pytest
is running (set HALO_RE_FORCE_SYNC=1 to sync under pytest).

Nothing here sends anything, reads anything outside the engagement tree
and the pack data dir, or writes the store — this is a read-only view
layer. Stdlib-only by pack convention.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from findings_store import FindingStore  # noqa: E402

# Finding.status enum: candidate, needs_validation, confirmed, not_reproduced,
# duplicate, rejected, requires_human_review, withdrawn.
# Display mapping: identified / reviewed / confirmed, where "reviewed" =
# independent reproduction done (validation.status=reproduced) but the judge
# has not confirmed yet.
TERMINAL_STATES = {"not_reproduced", "duplicate", "rejected", "withdrawn"}

SEVERITIES = ("critical", "high", "medium", "low", "info")


def display_state(f: dict) -> str:
    status = str(f.get("status", "")).lower()
    if status == "confirmed":
        return "confirmed"
    if status in TERMINAL_STATES:
        return status
    val = f.get("validation") or {}
    if isinstance(val, dict) and str(val.get("status", "")).lower() == "reproduced":
        return "reviewed"
    return "identified"


def _ext_data_dir() -> Path | None:
    """The harness's data-dir resolver, when halo_harness is importable."""
    try:
        from halo_harness.ext import data_dir as _harness_data_dir
        return Path(_harness_data_dir("halo-re"))
    except Exception:
        return None


def data_dir() -> Path:
    """The pack's DATA folder — where Studio's `data:` panel sources are
    served from (~/.halo/packs/.data/halo-re/). Env override first (tests,
    headless), then the harness resolver, then the convention."""
    d = (Path(os.environ.get("HALO_RE_DATA_DIR"))
         if os.environ.get("HALO_RE_DATA_DIR")
         else (_ext_data_dir()
               or Path.home() / ".halo" / "packs" / ".data" / "halo-re"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _severity(f: dict) -> str:
    return str(f.get("severity") or "info").lower()


def _source(f: dict) -> str:
    return str(f.get("source") or "tester")


def _updated(f: dict) -> str:
    hist = f.get("audit_history") or []
    if hist and isinstance(hist[-1], dict) and hist[-1].get("timestamp"):
        return str(hist[-1]["timestamp"])
    return ""


def _safe_id(finding_id: str) -> str:
    """finding_id pattern is ^[a-z0-9]+-[0-9]{2,}-[a-z0-9-]+$ already;
    still never trust a string that becomes a filename."""
    return re.sub(r"[^a-z0-9-]", "_", str(finding_id).lower()) or "_"


def summary_rows(store: FindingStore) -> list[dict]:
    """One table row per finding, display states applied."""
    rows = []
    for f in store.list_findings():
        rows.append({
            "finding_id": f.get("finding_id"),
            "title": f.get("title"),
            "severity": _severity(f),
            "state": display_state(f),
            "target_ref": f.get("target_ref", ""),
            "source": _source(f),
            "updated": _updated(f),
        })
    rows.sort(key=lambda r: (r["state"] != "confirmed", r["severity"], str(r["finding_id"])))
    return rows


def counts_markdown(engagement: dict, rows: list[dict]) -> str:
    """The counts strip: live states only, terminal states excluded."""
    n = {s: 0 for s in ("identified", "reviewed", "confirmed")}
    for r in rows:
        if r["state"] in n:
            n[r["state"]] += 1
    eng = engagement.get("engagement_id") or engagement.get("id") or ""
    return (f"**{n['identified']} identified · {n['reviewed']} reviewed · "
            f"{n['confirmed']} confirmed** — engagement `{eng}`\n")


def counts_row(engagement: dict, rows: list[dict]) -> dict:
    """The counts as one table row (the counts panel is a table: markdown
    panels cannot read the data folder)."""
    n = {s: 0 for s in ("identified", "reviewed", "confirmed")}
    for r in rows:
        if r["state"] in n:
            n[r["state"]] += 1
    return {
        "engagement": engagement.get("engagement_id") or engagement.get("id") or "",
        "identified": n["identified"],
        "reviewed": n["reviewed"],
        "confirmed": n["confirmed"],
    }


def detail_document(store: FindingStore, f: dict, *, generated: str) -> dict:
    """The full finding for a Studio browser's detail view: the stored
    document (every schema field, verbatim) plus a derived display state,
    the resolved evidence rows, and the summary row."""
    evidence_rows = []
    for ev in f.get("evidence") or []:
        row = {"ledger_ref": ev.get("ledger_ref"), "kind": ev.get("kind", "note"),
               "sanitized": bool(ev.get("sanitized", True)),
               "artifact_sha256": ev.get("artifact_sha256", "")}
        try:
            resolved = store.resolve_ledger_ref(ev.get("ledger_ref", ""))
            row.update({"seq": resolved.get("seq"), "actor": resolved.get("actor"),
                        "action": resolved.get("action"),
                        "artifact_sha256": resolved.get("artifact_sha256", "")})
        except Exception:
            row["unresolved"] = True
        evidence_rows.append(row)
    return {
        "finding": f,
        "display_state": display_state(f),
        "severity": _severity(f),
        "evidence_rows": evidence_rows,
        "generated": generated,
    }


def write_summary(engagement_root: Path, *, out_dir: Path | None = None) -> dict:
    """Write every panel file; returns what was written (for tests/CLI)."""
    store = FindingStore(Path(engagement_root))
    out = Path(out_dir) if out_dir else data_dir() / "findings"
    out.mkdir(parents=True, exist_ok=True)
    rows = summary_rows(store)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    engagement = store.engagement()
    (out / "summary.json").write_text(json.dumps(
        {"engagement_id": engagement.get("engagement_id")
                         or engagement.get("id") or "",
         "generated": generated, "rows": rows}, indent=1))
    (out / "counts.json").write_text(
        json.dumps([counts_row(engagement, rows)], indent=1))
    (out / "counts.md").write_text(counts_markdown(engagement, rows))
    written = []
    for f in store.list_findings():
        p = out / f"{_safe_id(f.get('finding_id', 'x'))}.json"
        p.write_text(json.dumps(detail_document(store, f, generated=generated),
                                indent=1))
        written.append(p.name)
    return {"rows": len(rows), "details": len(written), "dir": str(out),
            "generated": generated}


def finding_event(f: dict, *, actor: str = "") -> dict:
    """The re.finding event payload for a finding state moment."""
    return {
        "finding_id": f.get("finding_id"),
        "engagement_id": f.get("engagement_id"),
        "title": f.get("title"),
        "severity": _severity(f),
        "state": display_state(f),
        "source": _source(f),
        "target_ref": f.get("target_ref", ""),
        "binary": f.get("binary", ""),
        "function": f.get("function", ""),
        "actor": actor,
    }


def publish(f: dict, *, actor: str = "") -> bool:
    """Best-effort publish of a re.finding event to the Studio live feed.
    Never raises; returns whether the harness accepted it."""
    try:
        from halo_harness.ext import publish_event
        return bool(publish_event("halo-re", "re.finding",
                                  finding_event(f, actor=actor)))
    except Exception:
        return False


def _sync_disabled_under_pytest() -> bool:
    return ("PYTEST_CURRENT_TEST" in os.environ
            and os.environ.get("HALO_RE_FORCE_SYNC") != "1")


def attach(store: FindingStore) -> None:
    """Install the Studio change hook on a store: every mutation rewrites
    the panel files and publishes the re.finding event. Called from
    FindingStore.__init__ (best-effort); safe to call twice."""
    hook = getattr(store, "_studio_hook", None)
    if hook is not None:
        return

    def _hook(f: dict) -> None:
        if _sync_disabled_under_pytest():
            return
        try:
            write_summary(store.root)
        except Exception:
            pass  # a view failure must never fail the store
        try:
            actor = ""
            hist = f.get("audit_history") or []
            if hist and isinstance(hist[-1], dict):
                actor = str(hist[-1].get("actor", ""))
            publish(f, actor=actor)
        except Exception:
            pass

    store._studio_hook = _hook
    store.change_hooks.append(_hook)


def auto_root() -> Path | None:
    """The active engagement's root from the engage state, or None."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import engage
        s = engage.current()
        return Path(s["engagement_root"]) if s and s.get("engagement_root") else None
    except Exception:
        return None


if __name__ == "__main__":
    args = sys.argv[1:]
    out = None
    if "--data-dir" in args:
        i = args.index("--data-dir")
        out = Path(args[i + 1]) / "findings"
        del args[i:i + 2]
    if len(args) == 1 and args[0] == "auto":
        root = auto_root()
        if root is None:
            print("no active engagement — /hr engage first, or pass an "
                  "engagement root explicitly", file=sys.stderr)
            sys.exit(1)
    elif len(args) == 1:
        root = Path(args[0])
    else:
        print("usage: findings_view.py <engagement_root | auto> "
              "[--data-dir <path>]", file=sys.stderr)
        sys.exit(2)
    result = write_summary(root, out_dir=out)
    print(json.dumps(result))
