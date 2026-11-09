#!/usr/bin/env python3
"""Craft study tracker — the data layer for the pack's Craft & rebuild section.

Records craft-anything studies (the study -> build -> check -> ready
pipeline) in the pack DATA folder and writes the files the Studio section
declared in pack.yaml reads:

- craft/studies.json — every study, newest first: one row per study
  (study_id, target, target_kind, mode, stack, agent, status, updated).
  Studio's table panel accepts {"rows": [...]}.
- craft/counts.json — one row {studies, ready, in_progress} for the
  counts TABLE panel (markdown panels cannot read the data folder).
- craft/<study_id>.json — the FULL study record: what the Studio craft
  browser (studio/craft.js) fetches when you click into a study.

A study lifecycle: planned -> studying -> building -> checking -> ready,
or abandoned at any point. Modes are the craft-anything modes: clean-room
(default: nothing inside the original is read, only what a visitor sees)
and deep (reads code/files with its engines; pass --deep per run).

Studio sync: every write rewrites the panel files and publishes a
re.craft.study event to the Studio live feed (halo_harness.ext,
best-effort; never raises). The data folder is
~/.halo/packs/.data/halo-re/ (env HALO_RE_DATA_DIR overrides; the
harness's own resolver is used when importable) — NEVER the pack folder.

CLI (the skill drives this; you can too):
  python tools/craft_studies.py add --id cs-01-example --target <url|app|file>
      --kind web|app|game|binary [--mode clean-room|deep] [--stack "..."]
      [--output <dir>] [--agent claude|codex|acp:<name>] [--notes "..."]
  python tools/craft_studies.py update <id> [--status planned|studying|
      building|checking|ready|abandoned] [--notes "..."] [--output <dir>]
      [--mismatches N] [--check-note "..."]
  python tools/craft_studies.py list
  (global: --data-dir <path>)

Stdlib-only by pack convention.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("planned", "studying", "building", "checking", "ready", "abandoned")
MODES = ("clean-room", "deep")
KINDS = ("web", "app", "game", "binary")
IN_PROGRESS = ("planned", "studying", "building", "checking")


def _ext_data_dir() -> Path | None:
    try:
        from halo_harness.ext import data_dir as _harness_data_dir
        return Path(_harness_data_dir("halo-re"))
    except Exception:
        return None


def data_dir() -> Path:
    """The pack's DATA folder (~/.halo/packs/.data/halo-re/). Env override
    first, then the harness resolver, then the convention path."""
    d = (Path(os.environ.get("HALO_RE_DATA_DIR"))
         if os.environ.get("HALO_RE_DATA_DIR")
         else (_ext_data_dir()
               or Path.home() / ".halo" / "packs" / ".data" / "halo-re"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_id(study_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "_", str(study_id).lower()) or "_"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _craft_dir() -> Path:
    d = data_dir() / "craft"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _studies_path() -> Path:
    return _craft_dir() / "studies.json"


def _study_path(study_id: str) -> Path:
    return _craft_dir() / f"{_safe_id(study_id)}.json"


def _load() -> list[dict]:
    p = _studies_path()
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text())
    except Exception:
        return []
    return doc.get("rows", []) if isinstance(doc, dict) else (doc or [])


def list_studies() -> list[dict]:
    return _load()


def publish(study: dict) -> bool:
    """Best-effort publish of a re.craft.study event. Never raises."""
    try:
        from halo_harness.ext import publish_event
        return bool(publish_event("halo-re", "re.craft.study", {
            "study_id": study.get("study_id", ""),
            "target": study.get("target", ""),
            "mode": study.get("mode", "clean-room"),
            "status": study.get("status", "planned"),
            "stack": study.get("stack", ""),
            "agent": study.get("agent", ""),
        }))
    except Exception:
        return False


def _write_all(rows: list[dict]) -> dict:
    """Rewrite every panel file from the given rows; returns the counts.
    The caller passes its in-memory list — re-reading the disk here would
    drop the row it just appended."""
    generated = _now()
    (_craft_dir() / "studies.json").write_text(
        json.dumps({"generated": generated, "rows": rows}, indent=1))
    n = {"studies": len(rows), "ready": 0, "in_progress": 0}
    for r in rows:
        if r.get("status") == "ready":
            n["ready"] += 1
        elif r.get("status") in IN_PROGRESS:
            n["in_progress"] += 1
    (_craft_dir() / "counts.json").write_text(json.dumps([n], indent=1))
    return n


def add(study_id: str, target: str, kind: str, *, mode: str = "clean-room",
        stack: str = "", output: str = "", agent: str = "",
        notes: str = "") -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not re.match(r"^cs-[0-9]{2,}-[a-z0-9-]+$", study_id):
        raise ValueError("study_id must look like cs-NN-slug "
                         "(lowercase, digits, dashes)")
    rows = _load()
    if any(r.get("study_id") == study_id for r in rows):
        raise ValueError(f"study {study_id} already exists — use update")
    now = _now()
    study = {
        "study_id": study_id,
        "target": target,
        "target_kind": kind,
        "mode": mode,
        "stack": stack,
        "output": output,
        "agent": agent,
        "status": "planned",
        "notes": notes,
        "created": now,
        "updated": now,
    }
    rows.append(study)
    _write_all(rows)
    _study_path(study_id).write_text(json.dumps(study, indent=1))
    publish(study)
    return study


def update(study_id: str, *, status: str = "", notes: str = "",
           output: str = "", mismatches: int | None = None,
           check_note: str = "") -> dict:
    rows = _load()
    row = next((r for r in rows if r.get("study_id") == study_id), None)
    if row is None:
        raise ValueError(f"no such study: {study_id}")
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        row["status"] = status
    if notes:
        row["notes"] = notes
    if output:
        row["output"] = output
    if mismatches is not None:
        check = row.get("check") or {}
        check["mismatches"] = int(mismatches)
        if check_note:
            check["note"] = check_note
        row["check"] = check
    elif check_note:
        check = row.get("check") or {}
        check["note"] = check_note
        row["check"] = check
    row["updated"] = _now()
    _write_all(rows)
    _study_path(study_id).write_text(json.dumps(row, indent=1))
    publish(row)
    return row


def get(study_id: str) -> dict:
    p = _study_path(study_id)
    if not p.exists():
        raise ValueError(f"no such study: {study_id}")
    return json.loads(p.read_text())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="craft-anything study tracker")
    ap.add_argument("--data-dir", default=None, help="override the pack data folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--target", required=True)
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--mode", default="clean-room", choices=MODES)
    a.add_argument("--stack", default="")
    a.add_argument("--output", default="")
    a.add_argument("--agent", default="")
    a.add_argument("--notes", default="")
    u = sub.add_parser("update")
    u.add_argument("study_id")
    u.add_argument("--status", default="", choices=("",) + STATUSES)
    u.add_argument("--notes", default="")
    u.add_argument("--output", default="")
    u.add_argument("--mismatches", type=int, default=None)
    u.add_argument("--check-note", default="")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.data_dir:
        os.environ["HALO_RE_DATA_DIR"] = args.data_dir
    try:
        if args.cmd == "add":
            s = add(args.id, args.target, args.kind, mode=args.mode,
                    stack=args.stack, output=args.output, agent=args.agent,
                    notes=args.notes)
            print(json.dumps({"ok": True, "study": s["study_id"],
                              "status": s["status"]}))
        elif args.cmd == "update":
            s = update(args.study_id, status=args.status, notes=args.notes,
                       output=args.output, mismatches=args.mismatches,
                       check_note=args.check_note)
            print(json.dumps({"ok": True, "study": s["study_id"],
                              "status": s["status"]}))
        else:
            print(json.dumps(_load(), indent=1))
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
