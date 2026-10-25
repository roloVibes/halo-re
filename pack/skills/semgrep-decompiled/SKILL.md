---
name: semgrep-decompiled
description: >-
  Run semgrep/opengrep SAST rules over Ghidra decompiled output to mechanically
  surface memory-safety and API-misuse candidates in a binary, then LLM-triage
  each finding to real bug / false positive / needs more context. Use when the
  target is a compiled binary (no source) and you need rule-driven coverage of
  many functions before spending decompiler or analyst cycles on any one of them.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Semgrep over Decompiled Code

Ghidra's decompiler emits C that is close enough to real C that static-analysis
rules match it. That turns SAST into a binary-analysis tool: decompile every
function to disk as one `.c` file, run a community C ruleset over the tree, and
you get candidate double-frees, allocation-size integer overflows, unsafe API
calls, and use-after-free shapes across the whole binary in one pass — before
any LLM or analyst has looked at a single function. The findings are noisy
(decompiled code carries auto-generated names and reconstructed control flow),
so the second half of this skill is the triage pass that separates real bugs
from the known false-positive sources.

Tool names below refer to this pack's Ghidra MCP tools, which surface in a Halo
session as plugin tools from the MCP server `ghidra` (granted with
`halo pack enable halo-re --grant mcp:ghidra`).

## Use this skill when
- The target is a binary with no source available and you want broad,
  rule-driven vulnerability coverage instead of (or before) function-by-function
  reading.
- You are auditing a driver or large native library where manual review of
  every function is not feasible and you need a ranked candidate list.
- You have a decompiled tree on disk (or need to produce one) and want findings
  in a machine-readable form for LLM triage or reporting.

## Workflow Overview
1. **Confirm the target and decompile it to disk.** Run
   `ghidrecomp <binary> -o <outdir>` — this produces one `.c` file per function.
   Confirm the binary is what you expect first with the pack's `list_binaries`
   and `binary_metadata` tools if it is already in the Ghidra project.
   Fallback: if `ghidrecomp` is not installed, loop the pack's
   `decompile_function` tool over functions discovered via `search_functions`
   and write each result to the output tree — same layout, slower.
2. **Choose the scanner by output consumer.** This is the critical fork:
   - Human/text review only → plain `semgrep` is fine.
   - Anything that parses JSON (every LLM-triage pipeline) → **must use
     `opengrep`**. The OSS semgrep CLI strips `extra.lines` and
     `extra.metavars` from JSON output, writing `"requires login"` in their
     place — without those fields the triage model cannot see the matched code
     or the bound metavariables, and triage quality collapses. Opengrep takes
     the same rules and the same CLI shape but keeps the fields.
3. **Set the locale before invoking opengrep.** Export `LC_ALL=C.UTF-8`
   (e.g. `LC_ALL=C.UTF-8 opengrep scan ...`). Without it opengrep dies parsing
   rule YAML that contains an em dash — which community rulesets do contain.
4. **Fetch a ruleset and scan.** Clone the 0xdea community semgrep-rules repo,
   point `SEMGREP_RULES_DIR` at it, and run:
   `opengrep scan --config "$SEMGREP_RULES_DIR/rules/c/" <outdir>/ --no-git-ignore --json > results.json`
   The `--no-git-ignore` flag matters: decompiled output dirs are often inside
   git workspaces and findings would otherwise be silently skipped.
5. **Verify the fields survived.** Load `results.json` and assert that at least
   one finding has non-empty `extra.lines` and populated `extra.metavars`. If
   you see the literal string `requires login` in those fields, you ran OSS
   semgrep by mistake — go back to step 2. A JSON with stripped fields looks
   identical to a clean scan unless you check.
6. **Summarize before triaging.** Build a `collections.Counter` over rule ids
   and severities. This summary is the budget map: it tells you which rules
   dominate and where the cap in the next step actually bites.
7. **Bound the LLM budget.** Cap findings per rule at 30 (sort within a rule by
   severity, ERROR before WARNING). A driver can produce hundreds of hits under
   a single integer-wraparound rule; triaging all of them is how a scan turns
   into an unpayable bill. Note the cap and the dropped count in the output.
8. **LLM-triage each finding.** Feed the model the finding's `rule_id`,
   `severity`, `message`, `extra.lines` (the matched source), and
   `extra.metavars` (the bound variables), and require one of three verdicts:
   `real_bug`, `false_positive`, or `needs_more_context`. For
   `needs_more_context` verdicts, resolve the question with the pack's tools —
   `decompile_function` for the full function, `list_xrefs` or `gen_callgraph`
   for caller context — instead of asking the model to guess.

**What the rules actually catch on decompiled code:** double-free shapes
(`free(ptr)` reachable twice), allocation-size integer overflow
(`malloc(x * y)` with unchecked multiplication), API misuse (`gets`, `strcpy`,
`sprintf`), and use-after-free / free-of-stack-memory lifecycle patterns.

**Known false-positive sources — prime the triage on these:** (a)
auto-generated variable names — the decompiler names locals `local_18`-style by
offset, so a rule keyed on a freed variable can "match" identically named
locals in unrelated functions; (b) reconstructed control flow — the decompiler
emits `goto` and labels where the binary had structured control flow, which
breaks AST-adjacency assumptions in patterns that expect loops or blocks.
Verdicts of `false_positive` should name which of these (or something else)
fired.

## Output Schema
```json
{
  "binary": "ksthunk.sys",
  "decompiled_dir": "/tmp/decomp_ksthunk",
  "scanner": "opengrep",
  "ruleset": "0xdea/rules/c",
  "findings_total": 214,
  "summary_by_rule": [{"rule_id": "kernel-integer-wraparound", "count": 97, "severities": {"ERROR": 12, "WARNING": 85}}],
  "triage_cap_per_rule": 30,
  "triaged": [
    {
      "rule_id": "double-free",
      "severity": "ERROR",
      "file": "FUN_140001200.c",
      "metavars": {"$PTR": "local_18"},
      "verdict": "false_positive",
      "reason": "local_18 is an auto-generated name; the two frees are in unrelated functions",
      "confidence": 0.8
    }
  ],
  "real_bugs": ["...triaged entries with verdict real_bug..."],
  "needs_more_context": ["...entries pending tool follow-up..."]
}
```

## When NOT to Use This Skill
- You are investigating one specific function interactively — call
  `decompile_function` and reason about it directly; a whole-tree SAST pass is
  the wrong granularity.
- You have the original source code. Scan the source with semgrep proper
  (build-aware, no decompiler artifacts) instead of decompiling it first.
- The target is not compiled C/C++-shaped (e.g. pure bytecode/managed
  binaries) — decompiled-C rules will not match meaningfully.
- A clean scan must never be reported as proof of absence. Rules find what
  rules can find; logic flaws, auth bypasses, and design-level bugs are
  invisible to this pass.
