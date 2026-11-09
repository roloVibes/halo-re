#!/usr/bin/env python3
"""Engage-mode engine for halo-re — scope as data, not location.

A single active-engagement state file in the pack's data folder gates the
findings store and the /hr report command. Fail-closed: no valid,
in-window engagement record, no engagement.

Ported from the halo-hacker engage engine, state machinery only. Two
source features are deliberately DROPPED (halo-re has no use for them):
- lineup application (`engage(..., lineup=...)` and the state's lineup
  field) — halo-re applies no playbooks lineups on engage;
- scope-targets classification (extract_hosts/classify and the
  targets-count in the engage result) — halo-re's targets are local
  binaries, not network scope, and there is no PreToolUse scope guard.

Stdlib-only by pack convention.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _ext_data_dir() -> Path | None:
    """The harness's data-dir resolver, when halo_harness is importable."""
    try:
        from halo_harness.ext import data_dir as _harness_data_dir
        return Path(_harness_data_dir("halo-re"))
    except Exception:
        return None


def _data_dir() -> Path:
    """The pack's DATA folder (~/.halo/packs/.data/halo-re/) — the same place
    findings_view writes the Studio panel files. Env override for tests;
    convention fallback when the harness import is unavailable. NEVER the
    pack folder itself: runtime state must not land in the install unit."""
    d = (Path(os.environ.get("HALO_RE_DATA_DIR"))
         if os.environ.get("HALO_RE_DATA_DIR")
         else (_ext_data_dir()
               or Path.home() / ".halo" / "packs" / ".data" / "halo-re"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return _data_dir() / "engage-state.json"


def _history_path() -> Path:
    return _data_dir() / "engage-history.jsonl"


def _gate_log_path() -> Path:
    return _data_dir() / "gate-log.jsonl"


def _parse_window_ts(ts: str) -> float:
    """ISO-8601 (Z-suffixed in our fixtures); tolerant parse, never guesses."""
    t = str(ts).replace("Z", "+00:00")
    return datetime.fromisoformat(t).timestamp() if t else 0.0


def _now_ts() -> float:
    return time.time()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def load_engagement(engagement_root: Path) -> dict:
    """Read the engagement record from an engagement tree.

    The record that reaches here validates against
    schemas/re-engagement.schema.json: engagement.json is written only by
    FindingStore.create(), which schema-validates before writing. (The
    source engine relied on the same invariant; validation itself lives in
    the store, keeping this module stdlib-only.)"""
    path = Path(engagement_root) / "engagement.json"
    if not path.is_file():
        raise ValueError(f"engagement record not found: {path}")
    return _load_json(path)


def check_window(engagement: dict) -> tuple[bool, str]:
    """Return (ok, error_message). Fail-closed."""
    window = engagement.get("window") or {}
    start = window.get("start")
    expires = window.get("expires")
    if not start or not expires:
        return False, "engagement window missing start or expires"
    now = _now_ts()
    try:
        start_ts = _parse_window_ts(start)
        expires_ts = _parse_window_ts(expires)
    except Exception as e:
        return False, f"engagement window unparsable: {e}"
    if now < start_ts:
        return False, f"engagement window opens {start}; too early"
    if now > expires_ts:
        return False, f"engagement window expired {expires}; refusing"
    return True, ""


def state() -> dict | None:
    """Raw state file contents, or None if no state file. Does NOT check
    window expiry — callers that need runtime enforcement use current()."""
    path = _state_path()
    if not path.is_file():
        return None
    try:
        return _load_json(path)
    except Exception:
        return None


def current() -> dict | None:
    """The active engagement state, or None if none/expired."""
    s = state()
    if not s or not s.get("active"):
        return None
    try:
        engagement = load_engagement(Path(s["engagement_root"]))
    except Exception:
        return None
    ok, error = check_window(engagement)
    if not ok:
        return None
    return s


def is_engaged() -> bool:
    return current() is not None


def engage(engagement_root: Path) -> dict:
    """Validate engagement window and write active state. Fail-closed."""
    root = Path(engagement_root)
    engagement = load_engagement(root)

    ok, error = check_window(engagement)
    if not ok:
        return {"ok": False, "error": error}

    existing = state()
    if existing and existing.get("active"):
        return {
            "ok": False,
            "error": f"already engaged: {existing.get('engagement_id')} — disengage first",
        }

    s = {
        "engagement_id": engagement["engagement_id"],
        "engagement_root": str(root.resolve()),
        "engaged_at": _utc_now(),
        "active": True,
    }
    _write_json(_state_path(), s)

    return {
        "ok": True,
        "engagement_id": s["engagement_id"],
        "window_end": engagement["window"]["expires"],
    }


def status() -> dict:
    """Current engagement status, including remaining window seconds."""
    s = state()
    if not s or not s.get("active"):
        return {"ok": True, "active": False}

    try:
        engagement = load_engagement(Path(s["engagement_root"]))
    except Exception as e:
        return {"ok": False, "active": False, "error": f"cannot load engagement: {e}"}

    ok, error = check_window(engagement)
    if not ok:
        return {
            "ok": True,
            "active": False,
            "expired": True,
            "engagement_id": s.get("engagement_id"),
            "error": error,
        }

    expires_ts = _parse_window_ts(engagement["window"]["expires"])
    remaining = int(expires_ts - _now_ts())
    return {
        "ok": True,
        "active": True,
        "engagement_id": s.get("engagement_id"),
        "engagement_root": s.get("engagement_root"),
        "window_end": engagement["window"]["expires"],
        "window_remaining_seconds": remaining,
    }


def disengage() -> dict:
    """Write end-state to history and remove the active state file."""
    s = state()
    if not s:
        return {"ok": True, "active": False, "note": "no active engagement"}

    _append_jsonl(_history_path(), {
        "engagement_id": s.get("engagement_id"),
        "engaged_at": s.get("engaged_at"),
        "disengaged_at": _utc_now(),
    })

    _state_path().unlink(missing_ok=True)
    return {"ok": True, "active": False, "engagement_id": s.get("engagement_id")}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"ok": False, "error": "usage: engage.py engage <root> | status | disengage"}))
        sys.exit(2)

    cmd = args[0]
    if cmd == "engage":
        if len(args) < 2:
            print(json.dumps({"ok": False, "error": "engage requires an engagement root"}))
            sys.exit(2)
        print(json.dumps(engage(Path(args[1]))))
    elif cmd == "status":
        print(json.dumps(status()))
    elif cmd == "disengage":
        print(json.dumps(disengage()))
    else:
        print(json.dumps({"ok": False, "error": f"unknown command: {cmd}"}))
        sys.exit(2)


if __name__ == "__main__":
    _cli()
