#!/usr/bin/env python3
"""Leadership email renderer for confirmed RE findings only.

Outputs the five-part shape required by the communicate-findings skill:
subject = takeaway, opening paragraph, concrete impact, bounded ask,
full-report pointer. Stdlib-only; fail-closed on non-confirmed records.
"""
from __future__ import annotations

import urllib.parse
from typing import Any


BANNED_FUD_WORDS = frozenset(("catastrophic", "nightmare", "doomed"))
BANNED_FUD_PHRASES = ("hackers are coming", "under constant attack")


def _fail_unless_confirmed(findings: list[dict]) -> None:
    if not findings:
        raise ValueError("refusing to render leadership email: no confirmed findings provided")
    for f in findings:
        if f.get("status") != "confirmed":
            raise ValueError(
                f"refusing to render leadership email: finding {f.get('finding_id')} "
                f"is {f.get('status')}"
            )


def _engagement_target(findings: list[dict], engagement: dict) -> str:
    targets = sorted(
        {str(f.get("target_ref") or "").strip() for f in findings if f.get("target_ref")}
    )
    if len(targets) == 1 and targets[0]:
        return targets[0]
    return engagement.get("engagement_id") or engagement.get("id") or "the engagement"


def _severity_rank(f: dict) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return order.get(str(f.get("severity") or "info").lower(), 5)


def _strip_terminal_period(text: str) -> str:
    return text.rstrip().rstrip(".")


def _has_fud(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in BANNED_FUD_WORDS) or any(
        phrase in lowered for phrase in BANNED_FUD_PHRASES
    )


def _impact_verb_phrase(impact: str, target: str) -> str:
    """Return a sentence-ready verb phrase from an impact description."""
    impact = impact.lower().strip()
    verbs = ("poses", "creates", "enables", "allows", "grants", "leads", "exposes", "causes")
    if impact.startswith(verbs):
        return impact
    return f"exposes {target} to {impact}"


def render_leadership_email(findings: list[dict], engagement: dict) -> dict:
    """Return {"subject", "body", "mailto_url"} for a senior audience.

    Fail-closed: empty list or any finding whose status is not "confirmed"
    raises ValueError naming the offending finding id.
    """
    _fail_unless_confirmed(findings)

    target = _engagement_target(findings, engagement)
    count = len(findings)
    strongest = min(findings, key=_severity_rank)
    top_title = strongest.get("title") or "a confirmed finding"
    top_impact = _impact_verb_phrase(
        _strip_terminal_period(
            strongest.get("impact") or strongest.get("description") or "poses a business risk"
        ),
        target,
    )

    # Subject = takeaway: count + location + the ask.
    ask_in_subject = "decide remediation priority and schedule a walkthrough before the window closes"
    subject = f"{count} confirmed finding{'s' if count != 1 else ''} in {target} — {ask_in_subject}"

    # Opening paragraph: whole story in 2-3 sentences, business terms.
    opening = (
        f"We confirmed {count} issue{'s' if count != 1 else ''} in {target}. "
        f"The most significant, {top_title}, {top_impact}. "
        "This note summarizes the business impact and the one decision needed next."
    )

    # Impact: concrete, verb-first bullets. One bullet per finding.
    impact_bullets = []
    for f in findings:
        effect = _strip_terminal_period(
            f.get("impact") or f.get("description") or "a security weakness"
        )
        title = f.get("title") or "this issue"
        impact_bullets.append(
            f"Expose {target} to {effect.lower()} through {title}."
        )
    impact = "\n".join(f"- {b}" for b in impact_bullets)

    # The ask: one bounded recommendation with decision/timeframe.
    ask = (
        "- Decide which finding to remediate first and assign owners by the end of this week.\n"
        "- Schedule a 30-minute walkthrough with the engineering team before the engagement window closes."
    )

    # Pointer: where the full report lives and offer to walk through it.
    pointer = (
        "The full report with evidence references and remediation steps is in the engagement report directory. "
        "Reply or grab time on the calendar and we will walk through the findings and next steps."
    )

    body = f"{opening}\n\n{impact}\n\n{ask}\n\n{pointer}"

    if _has_fud(subject) or _has_fud(body):
        raise ValueError("leadership email contains FUD language")

    mailto_url = (
        "mailto:?subject="
        + urllib.parse.quote(subject, safe="")
        + "&body="
        + urllib.parse.quote(body, safe="")
    )

    return {"subject": subject, "body": body, "mailto_url": mailto_url}
