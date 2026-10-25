---
name: kernel-api-audit
description: >-
  Import-driven capability audit for a compiled binary (originally Windows kernel drivers,
  works on anything with an import table: .sys, .so, ELF). Answers "what can this module do
  once an attacker reaches it, and which function actually does the dangerous thing" by
  paging the import table, bucketing it into weighted capability classes, xref-ing every
  high-weight import, and quoting decompiled evidence from the hot callers. Emits a risk
  score (capped 100) with a triage verdict. Use when asked for a capability/risk assessment
  of a binary rather than a specific vulnerability hunt.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Kernel API Capability Audit

An import table is a confession: everything a binary resolves from the outside world is
something it intends to do. This skill turns that confession into a measured capability
profile — which dangerous capability classes are present, which callers actually invoke
them, and what the decompiled code does at those call sites. The output answers the two
questions a triage actually needs: what can this module do once reached, and which
specific function does the dangerous thing. The core discipline is that an import name is
a lead, never a finding — every claim about behavior is backed by quoted decompiled lines
from a real call site. All Ghidra work goes through the pack's read-only MCP tools
(mcp server "ghidra" in a Halo session): `list_binaries`, `list_imports`, `list_xrefs`,
`decompile_function`, `binary_metadata`.

## Use this skill when
- You need "what can this driver/module do" — a capability and attack-surface assessment,
  not a per-IOCTL vulnerability hunt.
- You want a repeatable, scored triage verdict to decide whether a binary deserves a deep dive.
- The target has an import table (.sys, .so, ELF — the method is format-agnostic).
- A report needs evidence-backed attribution: which function performs which dangerous act.

## Workflow Overview
1. **Confirm the target — do not import anything unprompted.** Call `list_binaries` first.
   Work on whichever binary is already loaded and say so in the output: `open_binary` runs
   full Ghidra analysis on first open (a minute for small binaries, far longer for drivers),
   so only call it if the user named a target that is not loaded, and confirm first.
   Match binary names as prefixes of the basename — Ghidra project names carry a `-<hash>` suffix.
2. **Page the entire import table.** Call `list_imports` with `limit=100`, then keep calling
   with increasing `offset` (200, 300, …) until a page comes back shorter than the limit or
   `more` is false. Do not audit a partial table — a missed page can hide the one import
   that changes the verdict. Call `binary_metadata` alongside to record what you audited.
3. **Bucket every import into a capability class.** Assign each imported symbol to exactly
   one class and note its weight:

   | Class | Weight | Examples |
   |-------|--------|----------|
   | ARBITRARY_MEMORY | 10 | MmMapIoSpace, MmMapLockedPagesSpecifyCache, ZwMapViewOfSection, RtlCopyMemory on raw pointers |
   | PROCESS_MANIPULATION | 8 | PsLookupProcessByProcessId, KeStackAttachProcess, ObReferenceObjectByHandle |
   | HOOK_CALLBACK | 7 | callback registration into kernel notify/callback arrays |
   | RAW_IO | 6 | direct port/physical-memory I/O |
   | REGISTRY | 4 | registry read/write APIs |
   | CRYPTO | 3 | hashing/encryption primitives |
   | USER_MEMORY | 3 (mitigating) | ProbeForRead, ProbeForWrite, MmGetSystemAddressForMdlSafe |
   | ALLOCATION | 2 | pool allocation families |
   | SYNCHRONIZATION | 1 | locks, events, waits |

4. **Xref every import with weight >= 4.** Call `list_xrefs` on the `__imp_<Name>` label —
   the thunk label is where calling functions point, not the bare external symbol. If the
   label has no references, retry the bare import name once before declaring the import
   unused. Collect the set of distinct calling functions. **An import with no call site is
   noise**: it is resolved but never invoked, and it contributes no callers to the score.
5. **Decompile the hot callers and quote the lines.** For each distinct caller of a
   weight>=4 import, call `decompile_function` (a unique substring of the caller's name is
   enough) and pull the exact lines around the dangerous call. The report's evidence field
   must contain those quoted lines — the assessment is evidence-backed, not inferred from
   an import name. If a caller decompiles to fewer than 5 lines, it is a thunk: follow its
   single callee and quote from there instead.
6. **Score and set the verdict.** Compute:
   `risk_score = sum(weight of each DISTINCT class present) + 2 x (number of distinct high-risk callers)`,
   capped at 100. Distinct matters — ten ARBITRARY_MEMORY imports count the class weight
   once; the second term grows only with genuinely different dangerous callers.
   Verdict thresholds: **>= 25 deep-dive**, **10-24 targeted review**, **< 10 low priority**.
7. **Emit the report.** Produce the JSON in the Output Schema below as the final step,
   naming the loaded binary it was computed against.

## Output Schema
```json
{
  "binary": "string (project name actually analyzed)",
  "imports_total": 0,
  "capabilities": [
    {"class": "ARBITRARY_MEMORY", "weight": 10, "imports": ["MmMapIoSpace"], "callers": ["FunctionA"]}
  ],
  "evidence": [
    {
      "caller": "FunctionA",
      "import": "MmMapIoSpace",
      "class": "ARBITRARY_MEMORY",
      "quoted_lines": "decompiled lines containing the call"
    }
  ],
  "mitigating": [
    {"caller": "FunctionB", "import": "ProbeForRead", "note": "probe precedes user-buffer deref"}
  ],
  "risk_score": 0,
  "verdict": "deep-dive|targeted review|low priority",
  "summary": "string"
}
```

## When NOT to Use This Skill
- The question is a specific vulnerability hunt on a driver's IOCTL surface — use the
  kernel-driver-ioctl-audit skill instead; this one scores capability, not per-handler safety.
- The user hands you a new binary and asks something else entirely — do not
  `open_binary` as a side effect of this skill; analysis is expensive and the answer is
  to ask.
- The binary has no import table (statically linked, shellcode, raw firmware) — there is
  nothing to bucket and the scoring model does not apply.
- You need a version-to-version comparison — use patch-diff-analysis; an import audit
  cannot see what changed between builds.
