---
name: model-eval-for-re
description: >-
  Mechanically evaluate a model's fitness for reverse-engineering work before
  routing tasks to it — an executable-oracle CrackMe ladder, a tool-call
  compliance probe with NATIVE/RAW/JSON-in-content classification, and a
  streaming/TTFT measurement — with results recorded in the model-census
  registry. Use before delegating decompilation reading, vuln identification,
  or MCP tool-calling to any model whose RE ability you have not measured.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Model Evaluation for Reverse-Engineering Work

Never route RE work to a model on advertised capability. A model can claim
tool-calling support in its documentation and then emit the tool call as prose
in the message body, silently breaking every downstream automation; a model can
top generic leaderboards and still fail to follow a decompiled loop. This skill
is the measurement battery: four CrackMe levels graded by executing the target
itself (the binary is the answer key), a compliance probe for tool-calling
behavior, and a streaming measurement that does not lie about latency. It feeds
the existing `/model-census` skill and its registry at
`~/.config/model-census/registry.md` — record results there so the next session
routes on measurement, not on datasheets.

The pack's Ghidra MCP tools (MCP server `ghidra` in a Halo session) supply the
realistic tool surface for the compliance probe.

## Use this skill when
- A candidate model (new local Ollama pull, new OpenRouter id, new backend) is
  about to receive RE tasks — decompilation explanation, vuln identification,
  `FUN_` rename suggestions, or Ghidra MCP tool calls.
- An agent pipeline mysteriously "calls" tools but nothing executes — the
  compliance probe distinguishes a real tool call from prose shaped like one.
- A registry entry for the model is missing, stale, or silent on RE-shaped
  tasks.

## Workflow Overview
1. **Assemble the CrackMe ladder.** Four small compiled targets of increasing
   difficulty, each with a checkable password:
   - **T1 — literal compare:** the password sits as a plaintext string in
     `.rodata`; the check is a string equality. Anyone who can read decompiled
     output passes.
   - **T2 — per-byte XOR:** the password is stored XOR-encoded; the check
     decodes each byte and compares. Requires following a small loop.
   - **T3 — opaque-predicate maze:** dead branches and a decoy string sit on
     top of a plaintext check. The model must resist the decoy and reason
     about which branch is live.
   - **T4 — bytecode VM:** input bytes are pushed through an interpreted op
     program; the model must read the interpreter, derive the transformation,
     and invert it to recover the accepted input.
2. **Prompt with shown work — not answer-only.** The naive pattern is "Reply
   with ONLY the password on the first line, then a one-line explanation."
   Measured trap: suppressing step-by-step makes capable models *guess*, and a
   lucky guess at T2–T4 scores identically to real analysis. Ask for the work
   (the decode logic, the live-branch reasoning, the VM instruction trace) and
   grade the reasoning alongside the answer. Also remember thinking is off by
   default over the API — set `reasoning_effort="high"` (or the provider's
   equivalent) to turn it on, or you are measuring the model with its brakes
   on.
3. **Grade by execution, never by eyeball.** For each level, run the target
   binary (or its check routine) with the model's proposed password and record
   pass/fail. The program is the answer key: no judgment call, no partial
   credit, no "that looks right."
4. **Run the tool-call compliance probe.** Prompt the model to invoke a
   specific tool with specific arguments — e.g. call `decompile_function` with
   address `0x140001234`, `include_comments` true (a schema with nested/typed
   parameters; the probe tests call emission, not execution against a live
   server). Classify the response:
   - **NATIVE** — the SDK's `tool_calls` structure is populated; the backend
     did the work.
   - **RAW** — the model emitted its own model-native tool-call tokens
     (e.g. `<tool_call>...</tool_call>`) that the backend did not normalize.
     Unusable without a shim; the shim must be measured too.
   - **JSON-in-content** — the call is a fenced JSON block in the message
     body. Salvageable: attempt lenient repair (unquoted keys, trailing
     commas, single quotes) before parsing.
   Score each response on `valid_json` / `correct_params` / `correct_values`
   — a model that names the tool but mangles the typed parameters is a
   pipeline bug waiting for its cue.
5. **Measure streaming and TTFT honestly.** Request streaming with
   `stream_options: {"include_usage": true}` and read the chunks with two
   rules: (a) the usage chunk arrives LAST with an **empty `choices` list** —
   read `chunk.usage` before touching `choices[0]`, or you crash or miscount
   on the final chunk; (b) skip reasoning/thinking deltas when timing
   first-token latency — thinking tokens must not count toward TTFT, or you
   will report a "fast" model that streams only after a long hidden think, or
   a "slow" one that was answering immediately behind a reasoning stream.
6. **Judge only on RE-shaped tasks.** The battery that matters:
   decompilation explanation (feed real `decompile_function` output, score
   factual accuracy against the binary), tool-call compliance with nested
   schemas (step 4), vuln identification on known-CVE functions, and `FUN_`
   rename suggestions (does the proposed name survive an analyst's read?).
   Generic benchmarks — MMLU, HumanEval, and friends — do not measure any of
   this; a strong general score is not evidence of RE ability.
7. **Record the results.** Write the per-level CrackMe scores, the compliance
   classification, and the TTFT/usage numbers into the model-census registry
   at `~/.config/model-census/registry.md` (via the `/model-census` skill) so
   routing decisions cite the measurement. Note the eval configuration
   (reasoning effort, temperature, date) — scores are only comparable when
   the harness is identical.
8. **Re-run on suspicion.** If a model's behavior in the field contradicts
   its registry scores (wrong-tool calls, phantom tool use, sudden quality
   drop), check for a floating alias resolving to a different model first,
   then re-run this battery before trusting either the old or the new
   observation.

## Output Schema
```json
{
  "model": "exact-model-id@provider",
  "evaluated_at": "2026-10-25",
  "config": {"reasoning_effort": "high", "temperature": 0.1, "streaming": true},
  "crackme": {
    "T1_literal_compare": {"passed": true, "password_verified_by_execution": true},
    "T2_xor_decode": {"passed": true, "password_verified_by_execution": true},
    "T3_opaque_predicate": {"passed": false, "password_verified_by_execution": false, "note": "followed the decoy string"},
    "T4_bytecode_vm": {"passed": false, "password_verified_by_execution": false}
  },
  "tool_call_compliance": {
    "classification": "JSON_IN_CONTENT",
    "valid_json": true,
    "correct_params": true,
    "correct_values": true,
    "note": "fenced JSON, lenient repair needed for unquoted keys"
  },
  "streaming": {
    "ttft_ms_excluding_reasoning": 412,
    "usage_chunk_read_before_choices": true,
    "usage": {"prompt_tokens": 1840, "completion_tokens": 220}
  },
  "re_task_scores": {
    "decompilation_explanation": 0.8,
    "vuln_identification": 0.6,
    "fun_rename_suggestions": 0.7
  },
  "verdict": "route for triage-tier RE only; not for tool-driven agent loops",
  "registry_updated": true
}
```

## When NOT to Use This Skill
- Do not use generic benchmark numbers (MMLU, HumanEval, chat-arena) as a
  substitute — they measure none of the four RE-shaped abilities above.
- Do not grade CrackMe answers by reading the model's explanation and agreeing
  with it. Only execution of the check routine counts; everything else is
  narrative.
- Do not run the battery once with thinking disabled and record the score as
  the model's ceiling — the default API posture hides the model's reasoning,
  and the low score will misroute every later decision.
- Do not skip the tool-call probe because "the backend says it supports
  tools." The probe exists precisely because claimed support and emitted
  behavior diverge — measured, not assumed.
- This skill does not pick the model for you; it produces the numbers. Routing
  decisions cite the registry entry.
