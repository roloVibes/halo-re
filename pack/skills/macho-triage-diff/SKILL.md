---
name: macho-triage-diff
description: >-
  macOS/iOS Mach-O (arm64/arm64e) triage and function-level diffing WITHOUT Ghidra, using
  local Python with LIEF + Capstone. Use when comparing two builds of an Apple binary to
  find changed functions fast (importing a 20k-function dylib into Ghidra takes ~40 min
  and blows RAM, and Linux binutils cannot read Mach-O at all). Normalizes relocation
  noise so two builds of an UNCHANGED function compare equal, separating real logic
  changes from adrp/branch churn.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Mach-O Triage and Function Diffing (No Ghidra)

Triage and compare macOS/iOS binaries locally, deterministically, and read-only. This
skill exists because the heavyweight path fails twice on Apple targets: binutils on Linux
cannot parse Mach-O at all, and Ghidra's import of a large dylib (~20,000 functions) runs
roughly 40 minutes of auto-analysis and exhausts RAM on the box. The alternative is a
Python stack — LIEF for structure, Capstone for arm64/arm64e disassembly — that answers
triage and "which functions changed between these two builds" in minutes. The technique
that makes diffing trustworthy is normalization: relocation-dependent operands are
rewritten to symbolic forms before comparison, so an unchanged function really does
compare equal across builds and whatever survives the diff is a genuine logic change.
No MCP/Ghidra tools are used by this skill — it is pure local Python via a shell.

## Use this skill when
- The target is a Mach-O binary (dylib, extension, framework, executable) on macOS/iOS.
- You have two builds of it and need to know which functions changed — fast, before any
  Ghidra/ghidriff work is justified.
- You need strings, symbols, or referenced strings triage on arm64/arm64e without Ghidra.
- The box cannot afford a Ghidra import (large dylib, shared machine, low RAM).

## Workflow Overview
1. **Set up the environment.** Work in a Python shell/script with `lief` and `capstone`
   installed (`uv pip install lief capstone` or the session's environment). FIRST call
   `lief.logging.disable()` — parsing a dyld-shared-cache extraction emits one warning
   per indirect-symbol entry, which is thousands of lines of noise that will bury your
   output. If the binary is a fat archive, take the slice explicitly (`fat.at(0)` when
   the FatBinary API is present, otherwise use the parse result directly).
2. **Parse and triage.** `lief.MachO.parse(path)` gives you sections, symbols, and
   libraries. Pull the basics for the report: architecture, sections, linked libraries,
   and exported symbols. Run strings over `__cstring` and `__oslogstring` — the latter is
   where Apple logs security rejections, which is a strong indicator of validation paths.
3. **Locate the function of interest.** Substring search over the symbol table
   (`find_symbol`-style helper); fall back to a raw address if the symbol is stripped.
   Bound the function with the next symbol's start plus the containing section's end —
   never disassemble past section boundaries.
4. **Map VA to bytes via sections.** Translate a virtual address to file bytes by
   finding the section whose range covers it and applying the section offset. This
   read_va mapping is the foundation for both disassembly and adrp/add string resolution.
5. **Disassemble with Capstone.** `Cs(CS_ARCH_ARM64, CS_MODE_ARM)` over the bounded byte
   range. Resolve what you can locally: `call_targets` should resolve each `bl` to the
   symbol name at its target (or mark it external); string references come from
   adrp/add pairs whose computed address lands in `__cstring`/`__oslogstring`.
6. **Normalize before any comparison — this is the core of the skill.** Produce the
   disassembly listing with:
   - addresses rebased to function-relative offsets (so a function that merely moved
     in the image still aligns);
   - `adrp` page operands rewritten to `<page>`;
   - adrp/add pairs rewritten to the **string they point at** (via the VA→section
     mapping), so string constants compare by content, not by address;
   - branch and call targets rewritten to `+0x…` (intra-function) or `<ext>`
     (out of function).
   The point: two builds of an UNCHANGED function then produce identical normalized
   listings — relocation noise is gone, and any residual difference is a real logic change.
7. **Diff the two builds.** For each function present in both, compute `semantic_delta`
   via `difflib.SequenceMatcher` over the normalized listings — it yields
   `{changed, identical, ratio}` plus the per-side listings. Present the changed ones
   side-by-side (aligned OLD|NEW with markers on divergent lines). Ratio 1.0 = unchanged;
   anything below needs a human/agent read of the changed lines — a very low ratio
   suggests a rewrite, not a patch (see the patch-diff-analysis skill for the
   decompiled-C follow-up).
8. **Report.** Emit the JSON below as the final step, listing changed functions with
   their ratios, the string/call-target evidence, and a clear note on how the diff was
   normalized.

## Output Schema
```json
{
  "binary_old": "string (path)",
  "binary_new": "string (path)",
  "arch": "arm64|arm64e",
  "triage": {
    "sections": ["..."],
    "libraries": ["..."],
    "strings_of_interest": [{"address": "0x...", "value": "...", "section": "__oslogstring"}]
  },
  "functions_compared": 0,
  "changed": [
    {
      "symbol": "string",
      "va_old": "0x...",
      "va_new": "0x...",
      "ratio": 0.87,
      "changed_lines": ["normalized listing lines that differ"],
      "call_targets": ["bl-resolved symbol names"],
      "assessment": "string: nature of the change"
    }
  ],
  "identical": 0,
  "summary": "string"
}
```

## When NOT to Use This Skill
- You need decompiled C or full structural analysis — that is Ghidra territory; use the
  pack's Ghidra tools (or the patch-diff-analysis skill once you know which functions
  changed). This skill reads assembly, not pseudocode.
- The target is PE/ELF — LIEF can parse them but the normalization rules here are
  arm64/adrp-specific.
- The function you need is not symbolized and has no reliable boundary — without a
  next-symbol bound, disassembly runs away; get the boundary another way first.
- The dylib has not been extracted from the dyld shared cache yet — extract the standalone
  binary first, then apply this skill.
