---
name: patch-diff-analysis
description: >-
  Comparative analysis of two builds of the same binary (CVE patch diffing): generate or
  accept a ghidriff diff, triage the function-match JSON by similarity to find the handful
  of changed functions among thousands, then decompile only those and read what validation
  the patch added. Handles the complete-rewrite case where byte-diffing is meaningless.
  Use when handed old+new versions of a binary, a patched CVE, or a ghidriff JSON file.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Patch Diff Analysis

When a vendor ships a fix, the delta between the old and new build is usually tiny —
a few functions out of thousands — but finding those functions by searching blind burns
decompiler cycles and attention. This skill inverts the cost model: compute (or accept) a
structural diff first, let its per-function similarity ranking point at exactly what
changed, and only then decompile. The analytical question at each changed function is
always the same and always semantic: **what validation was added?** Diffs at two scales
are handled differently — a near-identical pair is patched code to compare closely, while
a low-similarity pair means the vendor rewrote the function, and the lesson is in the
design change, not the bytes. Decompilation goes through the pack's read-only MCP tools
(mcp server "ghidra" in a Halo session): `list_binaries`, `open_binary`,
`decompile_function`, `search_functions`.

## Use this skill when
- You have two builds of the same binary (vulnerable + patched, or any old/new pair).
- You are handed a ghidriff JSON diff and asked what changed / where the fix is.
- A CVE was patched in a library or driver and you must identify the fixed function(s).
- You want to verify whether a public advisory's named functions match what the diff shows.

## Workflow Overview
1. **Obtain the diff.** If a pre-computed ghidriff JSON exists, use it — diffing is the
   expensive part and re-running it wastes 10+ minutes on large binaries. Otherwise generate
   it yourself:
   `uvx ghidriff --engine VersionTrackingDiff --output-path <dir> <old-binary> <new-binary>`
   Run this from a shell before any MCP work; it needs a Ghidra install but not the pack's
   MCP server.
2. **Triage the JSON before decompiling anything.** Parse the function-match array. Each
   entry carries a `similarity` field where 1.0 means identical. List every function with
   `similarity < 1.0`, **sorted ascending** — the most-changed function comes first, which
   is usually the fix itself. This is how you find 4 modified functions in a 20,000-function
   library without a single decompiler cycle.
3. **Separate named from generic matches.** A match named `TType1ParsingContext::SpecialEncoding`
   recovered a real symbol; `FUN_0041d000` / `sub_2a4f0` / `thunk_FUN_…` placeholders mean no
   symbol was recovered. Track `named_changed` and `generic_changed` as separate lists and
   prefer the named entries — they are directly queryable and far more likely to be the
   security-relevant fix. Generic entries need address-based lookup instead.
4. **Load both binaries.** Call `list_binaries`. You need old AND new in the project to
   compare decompilations; if either is missing, confirm with the user before calling
   `open_binary` (first open runs full analysis — expensive, and on a big dylib it can be
   tens of minutes). Remember project names carry a `-<hash>` suffix; match by prefix.
5. **Decompile only the changed functions, in both builds.** For each changed function,
   call `decompile_function` twice — once with `binary=<old>` and once with `binary=<new>`
   — using the function name (or entry-point address for generic matches). Do not
   decompile unchanged functions; the similarity field already cleared them.
6. **Read the delta semantically: what validation was added?** Compare the two
   decompilations line by line for new guards. The recurring fix vocabulary:
   bounds checks on attacker-controlled offsets, length validation before copies,
   integer-overflow guards (`add_overflow` / equivalent checked arithmetic), sign-bit
   validation on parsed values, and audit logging of rejected inputs (`os_log` on Apple
   platforms — a strong "this input was the attack vector" tell).
7. **Handle the complete-rewrite case deliberately.** A similarity around 0.35 does not
   mean 65% of the function changed — it means the vendor **rewrote** it. Do not byte-diff
   a rewrite; ask instead what design change the rewrite embodies. The canonical shape:
   fragile positional byte checks (e.g. comparing specific offsets against `.` and `/`)
   replaced by full-string traversal validation (scan the entire string for the forbidden
   pattern, with a proper `..` predicate), plus audit logging of everything rejected.
   A rewrite tells you the original approach was structurally unsound, not merely buggy —
   that is a stronger finding than the individual bug.
8. **Cross-check and report.** If a public advisory names functions, check whether the
   diff-guided route found the same ones — agreement is confirmation, disagreement is a
   lead (either the advisory missed something or the diff caught unrelated churn).
   Emit the JSON below as the final step, quoting decompiled lines for every claim.

## Output Schema
```json
{
  "old_binary": "string",
  "new_binary": "string",
  "diff_source": "generated|pre-computed",
  "matched": 0,
  "changed": [
    {
      "name": "string (or address for generic matches)",
      "similarity": 0.35,
      "named": true,
      "rewrite": true,
      "validation_added": ["full-string traversal check", "add_overflow guard", "sign-bit validation", "os_log audit of rejected inputs"],
      "evidence": {"old": "quoted decompiled lines", "new": "quoted decompiled lines"},
      "assessment": "string: what the change fixes and how"
    }
  ],
  "named_changed": 0,
  "generic_changed": 0,
  "advisory_cross_check": "string (agreement/disagreement with any public advisory, or 'none checked')",
  "summary": "string: root-cause reading of the patch"
}
```

## When NOT to Use This Skill
- You have only ONE build — there is nothing to diff; use kernel-api-audit or
  kernel-driver-ioctl-audit for single-binary analysis.
- The pair are not the same binary (different products, different compile of unrelated
  code) — VersionTrackingDiff noise will swamp any signal.
- The targets are Mach-O builds and you only need function-level changed/unchanged
  answers — the macho-triage-diff skill does that locally in minutes without Ghidra;
  come here when you need decompiled-C comparison of the changed functions.
- No Ghidra install and no pre-computed JSON exists — `uvx ghidriff` requires a local
  Ghidra; ask before setting one up.
