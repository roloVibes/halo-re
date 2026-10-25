---
name: ghidra-mcp-usage
description: >-
  How to drive the halo-re read-only Ghidra MCP tools correctly: list
  binaries first, prefix-match hash-suffixed names, page imports, xref
  the __imp_ label, and treat open_binary as the expensive operation it
  is. Use it whenever a Halo session will call any halo-re_ghidra tool,
  so queries return data instead of error dicts.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Ghidra MCP Usage — driving the pack's analysis tools

The pack ships one read-only Ghidra MCP server (mcp/ghidra_server.py,
MCP server name `ghidra`; in a Halo session the tools surface under the
`halo-re_ghidra` prefix). Twelve tools, one open project behind them:
`list_binaries`, `binary_metadata`, `open_binary`, `search_functions`,
`search_strings`, `list_imports`, `list_exports`, `decompile_function`,
`disassemble`, `read_bytes`, `list_xrefs`, `gen_callgraph`. Every tool
returns a compact JSON dict; failures come back as `{"error": ...}` with
the next action in the message — never a crash. Results are capped at
60,000 chars: narrowing the query is the remedy, not retrying.

## Use this skill when
- any task will query a binary through the halo-re ghidra tools
- a tool returns "no open binary matches ..." (hash-suffix prefix rule,
  step 2) or "is ambiguous" (step 5)
- preparing a session for a large target (two-stage flow, step 7)
- an import's call sites are needed (xref the `__imp_` label, step 6)

## Workflow Overview

1. **Call `list_binaries` FIRST, always.** It names every binary already
   in the open project so you never import what you already have, and it
   tells you what `binary=` values are valid. On a broken environment it
   is also the cheapest probe (it answers with the remedy instead of
   hanging; see the ghidra-doctor skill).
2. **Match binary names by prefix.** Ghidra stores project binaries under
   names with a `-<hash>` suffix (e.g. `ls-1f2a3b`), so pass the file-name
   prefix (`binary="ls"`, `binary="clfs.sys"`) — exact match wins, then
   case-insensitive prefix. With exactly one binary open you may omit
   `binary=` entirely; with several, always pass it.
3. **Read WHERE facts with `binary_metadata`** (processor, endian,
   executable format, function count, image base) before deeper queries —
   function count is also your cost estimate for step 7's analysis time.
4. **Import deliberately with `open_binary(path)`.** First open of a
   binary runs full Ghidra auto-analysis: ~1 minute for something like
   `/bin/ls`, minutes for a driver, roughly 40 minutes for a
   20,000-function dylib — and it holds the session busy the whole time.
   Confirm the target with the user before calling unless they named it.
   Re-opens of the same binary are instant (`status: "already-open"`).
5. **Find functions with `search_functions(query)`** (case-insensitive
   substring, default limit 10; shorter query on a miss). Then
   `decompile_function(name_or_address)` accepts an exact function name,
   a `0x...` address, or a substring — but a substring matching several
   functions returns the candidate list (first 10 names), which is a
   feature: pick one and retry. The entry-point lookup falls back to
   `GsDriverEntry`/`entry` when `DriverEntry` is absent, since CRT stubs
   tail-call the real entry. Use `disassemble` for raw instructions and
   `read_bytes` for hex at an address when decompiled C is not enough.
6. **Page imports and xref them correctly.** `list_imports` pages with
   `offset`/`limit` (default 100) — keep calling with a higher offset
   until a short page comes back (`more: false`). To find who *calls* an
   import, `list_xrefs` its `__imp_<Name>` label, not the bare external
   symbol — calling functions point at the `__imp_` thunk. Use
   `gen_callgraph(seed, direction="callers"|"callees")` for a trimmed
   edge list (it reports how much it trimmed).
7. **Two-stage flow for big targets: pre-analyze once, then serve.**
   Import the target into the persistent project (~/ghidra-projects) in
   a first stage — via `open_binary` in a scratch session, or
   `support/analyzeHeadless` — so the analysis cost is paid exactly once.
   Serve analysis from the finished project afterwards. Do not let an
   MCP client connect while the server is still chewing a cold import:
   the client handshake during the wait-for-analysis window times out and
   the failure looks like a broken server when it is only a busy one.
   Binaries named in the `HALO_RE_BINARIES` env var at server startup
   skip the open round-trip entirely.
8. **Hunt evidence with `search_strings`** (substring filter, default
   limit 50) for C2 URLs, paths, registry keys, and format strings, and
   `list_exports` for the entry surface — both accept the same `binary=`
   prefix matching as everything else.

## Output Schema
```json
{
  "skill": "ghidra-mcp-usage",
  "session": {"binaries": ["ls-1f2a3b"], "resolved_by_prefix": true},
  "queries": [
    {"tool": "decompile_function", "args": {"name_or_address": "main"}, "status": "ok"}
  ],
  "errors_encountered": [{"tool": "list_xrefs", "error": "no function matches 'connect'", "remedy": "xref __imp_connect instead"}],
  "notes": ["imports paged: 3 pages, 247 total"]
}
```

## When NOT to Use This Skill
- The environment itself is broken — that is the ghidra-doctor skill's
  job (install, deps, project dir).
- Running the server or wiring transports (MCPO, HTTP, stdio) — this
  skill is about calling the tools, not hosting them.
- Deciding *whether* to import a binary at all — the binary-triage skill
  answers that with cheap CLI checks before any Ghidra cost is paid.
- Anything requiring writes (rename, annotate, patch): the surface is
  read-only by construction; no tool here mutates the project.
