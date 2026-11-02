#!/usr/bin/env python3
"""Full RE findings report renderer for confirmed records only.

Produces a one-page executive summary followed by per-finding sections in a
parallel template: finding title → summary → impact → conditions → remediation
→ references → evidence (appendix pointer). Stdlib-only; fail-closed on
non-confirmed records.
"""
from __future__ import annotations


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _fail_unless_confirmed(findings: list[dict]) -> None:
    if not findings:
        raise ValueError("refusing to render full report: no confirmed findings provided")
    for f in findings:
        if f.get("status") != "confirmed":
            raise ValueError(
                f"refusing to render full report: finding {f.get('finding_id')} "
                f"is {f.get('status')}"
            )


def _severity_rank(f: dict) -> int:
    return SEVERITY_ORDER.get(str(f.get("severity") or "info").lower(), 5)


def _engagement_target(findings: list[dict], engagement: dict) -> str:
    targets = sorted(
        {str(f.get("target_ref") or "").strip() for f in findings if f.get("target_ref")}
    )
    if len(targets) == 1 and targets[0]:
        return targets[0]
    return engagement.get("engagement_id") or engagement.get("id") or "the engagement"


def _strip_terminal_period(text: str) -> str:
    return text.rstrip().rstrip(".")


def _impact_verb_phrase(impact: str) -> str:
    """Return a sentence-ready verb phrase from an impact description."""
    impact = impact.lower().strip()
    verbs = ("poses", "creates", "enables", "allows", "grants", "leads", "exposes", "causes")
    if impact.startswith(verbs):
        return impact
    return f"exposes the organization to {impact}"


def _finding_heading(f: dict) -> str:
    target = f.get("target_ref") or "the target"
    return f"## Finding {f['finding_id']}: {f['title']} affects {target}."


def render_full_report(findings: list[dict], engagement: dict) -> dict:
    """Return {"title", "markdown"} for the selected confirmed findings.

    Fail-closed: empty list or any finding whose status is not "confirmed"
    raises ValueError naming the offending finding id.
    """
    _fail_unless_confirmed(findings)

    eng_id = engagement.get("engagement_id") or engagement.get("id") or "this engagement"
    target = _engagement_target(findings, engagement)
    ordered = sorted(findings, key=_severity_rank)
    strongest = ordered[0]

    # Title = the strongest finding stated as impact.
    impact_phrase = _strip_terminal_period(
        strongest.get("impact") or strongest.get("description") or "business risk"
    )
    title = f"{strongest['title']} — {impact_phrase.lower()}"

    lines: list[str] = [f"# {title}", ""]

    # Page-one executive summary.
    count = len(ordered)
    top_impact = _impact_verb_phrase(
        _strip_terminal_period(
            strongest.get("impact") or strongest.get("description") or "poses a risk"
        )
    )
    lines += [
        "## Executive summary",
        "",
        (
            f"Engagement `{eng_id}` has {count} confirmed finding{'s' if count != 1 else ''} "
            f"in {target}. The highest-severity issue, {strongest['finding_id']} "
            f"({strongest['title']}), {top_impact}. We independently reproduced "
            "each finding and verified its evidence chain. Fix the highest-severity issue first, "
            "then work through the remainder in severity order."
        ),
        "",
    ]

    # Per-finding sections — one parallel template.
    for f in ordered:
        lines += [_finding_heading(f), ""]

        lines += ["### Summary", "", f.get("description") or "No description recorded.", ""]

        lines += ["### Impact", "", f.get("impact") or f.get("description") or "n/a", ""]

        lines += ["### Conditions", ""]
        prerequisites = f.get("prerequisites") or []
        if prerequisites:
            for pre in prerequisites:
                lines.append(f"- {pre}")
        else:
            lines.append("- No special conditions were identified.")
        lines.append("")

        lines += [
            "### Remediation",
            "",
            f.get("remediation") or "No remediation recorded.",
            "",
        ]

        lines += ["### References", ""]
        lines.append(f"- Category: {f.get('category') or 'n/a'}")
        if f.get("playbook"):
            pb = f["playbook"]
            lines.append(f"- Playbook: {pb.get('id')} v{pb.get('version')}")
        if f.get("binary"):
            lines.append(f"- Binary: {f['binary']}")
        if f.get("function"):
            lines.append(f"- Function: {f['function']}"
                         + (f" (CWE: {f['cwe']})" if f.get("cwe") else ""))
        elif f.get("cwe"):
            lines.append(f"- CWE: {f['cwe']}")
        lines.append(f"- Source: {f.get('source') or 'tester'}")
        lines.append("")

        lines += [
            "### Evidence",
            "",
            "See Appendix A for the complete evidence ledger references.",
            "",
        ]

    # Appendix: evidence ledger refs.
    lines += ["## Appendix A: Evidence ledger references", ""]
    for f in ordered:
        refs = [str(ev.get("ledger_ref") or "n/a") for ev in f.get("evidence") or []]
        lines.append(f"- **{f['finding_id']}**: {', '.join(refs)}")
    lines.append("")

    return {"title": title, "markdown": "\n".join(lines)}
