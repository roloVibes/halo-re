---
name: token-budget-a-binary
description: >-
  Measure a binary's decompiled-token cost before prompting any model:
  ghidrecomp to one .c per function, tiktoken cl100k_base sum, compare
  against the target model's usable context (ctx x 0.8). Use it before
  pasting decompiled code into any LLM so the context decision is
  arithmetic, not hope.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Token-Budget a Binary — measure before you prompt

Feeding a binary to a model starts with a budget question: does the
whole decompilation fit in the target model's context window, or does
the work have to be per-function / tool-driven? This skill answers it
mechanically — decompile everything to disk once, count tokens with the
cl100k_base tokenizer, and compare against the usable window. No
guessing, no pasting 90 KB of C into a chat to see what happens.

Two constants keep the arithmetic honest: decompiled C averages
**3–4 characters per token**, and the usable window is
**ctx × 0.8** (reserve ~20% for system prompt and output). If your
chars-per-token ratio drifts far outside 3–4, something other than
decompiled C crept into the corpus — find it before trusting the sum.

## Use this skill when
- planning to feed decompiled code from any binary to any model
- choosing between whole-context analysis, per-function prompting, and
  tool-driven (MCP) analysis
- a model silently truncated or drifted mid-analysis on a big paste —
  re-measure instead of retrying
- justifying a rename pass: Ghidra default names inflate the token bill
  (step 7)

## Workflow Overview

1. **Decompile all to disk**: `ghidrecomp <binary> -o <outdir>`. This
   wraps Ghidra headless and runs the ~30-analyzer auto-analysis pass;
   expect minutes for small binaries and much longer for large ones,
   plus noisy-but-benign warnings (pcode errors on PLT/EXTERNAL blocks,
   unresolved libc symbols, GNU-hash markup failures). It runs headless
   (`-Djava.awt.headless=true`).
2. **Locate the corpus**: the output lands as **one `.c` file per
   function** under `<outdir>/results/bins/<name>-<md5>/decomps/`. Find
   it programmatically (e.g. `Path(outdir).rglob("decomps")`, then glob
   `*.c`) rather than by eyeballing — the hashed directory name is not
   predictable. Record the function count.
3. **Count tokens**: for each `.c` file, `enc.encode(text)` with
   tiktoken's `cl100k_base` encoding and sum. Track the largest single
   function too — a corpus that fits in aggregate can still contain one
   function that does not.
4. **Sanity-check the ratio**: total chars / total tokens should land
   in 3–4. Report it; treat an outlier ratio as a corpus problem first.
5. **Compare against the target model**: usable = ctx × 0.8. Example
   arithmetic: a ~180-token average function yields roughly 145
   functions in a 32K window, ~568 in 128K, ~888 in 200K. Name the
   model and its ctx in the report so the verdict is reproducible.
6. **Emit the verdict** (exactly one):
   - `whole-binary-fits` — sum ≤ usable: the entire corpus can go in
     one context (still page it; see step 8).
   - `per-function` — the corpus exceeds usable but individual
     functions fit: prompt function-by-function (or in small batches),
     guided by xrefs/callgraph from the ghidra-mcp-usage skill.
   - `needs tool-driven` — the corpus vastly exceeds usable and the
     task is exploratory: don't shuttle context at all; drive
     list_binaries / search_functions / decompile_function /
     list_xrefs as MCP tool calls so the model pulls only what each
     step needs.
7. **Price in the name tax.** Hex addresses like `0x00401000` cost 3–5
   tokens each, and Ghidra's default names — `FUN_00401000`, `pcVar1`,
   `sVar2` — shatter into multiple BPE subwords while a human name like
   `parse_header` is a single token or two. A rename pass therefore
   buys readability AND budget at the same time; when the verdict is
   near the boundary, estimate the post-rename sum before deciding the
   corpus doesn't fit.
8. **Report** the JSON below, including the top-N largest functions by
   token count — those are the candidates for the per-function lane or
   for a rename pass first.

## Output Schema
```json
{
  "skill": "token-budget-a-binary",
  "binary": "/abs/path/to/binary",
  "corpus": {"outdir": "/abs/path/out", "decomps_dir": ".../results/bins/<name>-<md5>/decomps", "functions": 43, "total_chars": 210000},
  "tokens": {"encoding": "cl100k_base", "total": 62000, "mean_per_function": 1442, "largest_function": {"name": "FUN_00401f00", "tokens": 5100}},
  "chars_per_token": 3.39,
  "target": {"model": "named-model", "context_window": 128000, "usable": 102400},
  "verdict": "whole-binary-fits | per-function | needs tool-driven",
  "verdict_rationale": "62000 tokens <= 102400 usable; fits with headroom for prompt+output",
  "top_functions_by_tokens": [{"name": "FUN_00401f00", "tokens": 5100}]
}
```

## When NOT to Use This Skill
- No model is involved (pure human review of decompiled code) — token
  arithmetic is irrelevant.
- The binary hasn't been triaged yet — binary-triage comes first; don't
  pay a ghidrecomp pass on a sample that would be parked anyway.
- You need one function *now*: a single `decompile_function` call
  (ghidra-mcp-usage) is cheaper than a whole-corpus pass.
- Estimating cost for non-C artifacts (raw disassembly, binaries,
  blobs): the 3–4 chars/token constant is measured on decompiled C and
  does not transfer.
