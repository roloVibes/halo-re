---
description: Generate a leadership email or full report from confirmed RE findings.
argument-hint: "<finding-ids | --confirmed> [--for leadership|full]"
---

# /hr report

Render confirmed findings into a leadership email or full report.

1. Identify the active engagement root and load its engagement.json
   (use `pack/tools/engage.py` — the active state, fail-closed).
2. Read the requested findings from the FindingStore (`pack/tools/findings_store.py`),
   or all confirmed when `--confirmed`.
3. Reject any finding whose status is not `confirmed`; fail closed with the finding id.
4. Call `pack/reporting/leadership_email.py` or `pack/reporting/full_report.py`.
5. Write the artifacts into `<engagement_root>/report/`:
   - `leadership_email.json` and `leadership_email.md`
   - `full_report.md` (when `--for full` or both)
6. Present the file paths and the mailto URL so the user can review before sending.

Use `--for leadership` for the short email, `--for full` for the detailed report.
The pack generates drafts; it never sends email on its own.
