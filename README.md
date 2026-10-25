# halo-re

A reverse-engineering capability pack for
[Halo Harness](https://github.com/roloVibes/Halo-Harness): a read-only
Ghidra MCP server, procedural RE skills distilled from agentic-RE training,
kernel-driver and patch-diff audit playbooks, analysis agent roles, and
triage/static-sweep workflows.

```
halo pack install <this-repo>/pack
halo pack enable halo-re --grant mcp:ghidra --grant bash
```

## What it adds to Halo

| Piece | What it is |
|---|---|
| **Ghidra MCP server** (`pack/mcp/`) | FastMCP stdio server over pyghidra: `decompile_function`, `disassemble`, `search_functions`, `search_strings`, `list_imports`/`list_exports`, `list_xrefs`, `gen_callgraph`, `read_bytes`, `binary_metadata`, `list_binaries`, `open_binary`. Read-only by construction: no rename/delete/save tools exist. |
| **11 skills** (`pack/skills/`) | Procedural know-how: Ghidra bring-up and usage, binary triage, token budgeting, kernel IOCTL audit, kernel API audit, patch-diff analysis, Mach-O triage/diff, semgrep-on-decompiled, agent security posture, model evaluation for RE. |
| **5 agent roles + 4 lineups** | orchestrator, triage, analyst (drives the Ghidra tools), vuln-reviewer (read-only judge), reporter; lineups for triage, kernel-driver audit, patch diff, semgrep triage. |
| **8 playbooks** | Structured workflows with impact classes and evidence requirements — all read-only/low-impact toward the world. |
| **2 Halo workflows** | `halo workflow run halo-re/triage --input binary=<path>` and `halo-re/semgrep-triage` — multi-stage, judged, gated pipelines that compile to Orchestra goals. |
| **Artifacts + events** | The `re-finding-report` artifact schema and `re.finding` / `re.session` events for the Studio live feed. |

## Ghidra: needed, never bundled — but downloadable on demand

Ghidra is ~570 MB and licensed Apache-2.0 — the pack does not ship it. It
ships everything else:

- an install **doctor** (detects by effect — no `which ghidra`, there is
  no such binary; auto-detect globs `ghidra_*_PUBLIC` under `~/Documents`,
  `~/Downloads`, `~` and the tools dir);
- an **on-demand installer**: when no install is found, the doctor offers
  "download the latest official release?" and runs
  `install_tools.py --tool ghidra --yes` — it downloads from
  github.com/NationalSecurityAgency/ghidra/releases, checks the JDK
  (21+), extracts into the tools dir (default `~/halo-re-tools`, config
  key `tools_dir`), fixes the exec bits release zips lose, verifies by
  effect, and persists the path (`halo config set
  packs.settings.halo-re.ghidra_install_dir <path>`) so the pack always
  knows where it is. **Platform fallback included**: a release that ships
  no natives for your OS (measured: Ghidra 12.2+ dropped the macOS
  decompiler) is rejected and the previous release tried automatically.
- the same installer handles the optional **REA** (Reverse Engineer
  Anything) release: `--tool rea --yes` (~98 MB, MIT, Windows exe).
- Python deps for the MCP server: `pyghidra` + `mcp>=1.2,<2` in the
  Python Halo runs under (the doctor names the exact command).

Every measured trap — dot-prefixed project paths, GHIDRA_INSTALL_DIR
inheritance, the fresh-import analysis gap, the two-stage start, the zip
exec-bit loss — is in
[pack/docs/GHIDRA-NOTES.md](pack/docs/GHIDRA-NOTES.md) and baked into the
code.

## What is NOT in this pack

- No Ghidra binary, no target binaries, no sample data.
- No methodology corpus: the skills are original prose distilling
  techniques and constants (facts and patterns), credited to their
  sources in [pack/resources/REPOS.md](pack/resources/REPOS.md). Nothing
  from any course's notebooks is reproduced.
- No active/dynamic analysis: no execution of targets, no debugging, no
  fuzzing. The schema itself forbids impact above `low-impact` (a local
  Ghidra project write).

## Status

0.1.0 — validated against halo 3.2.1.0: `halo pack inspect` reports
`problems: none`; the MCP server is smoke-tested end-to-end against a
real Ghidra 12.1.2 install (decompile through stdio JSON-RPC, all 12
tools).

## License

Copyright © 2026 **Pinball Genie LLC**. All rights reserved — no
open-source reuse rights are granted. See `/LICENSE`.
