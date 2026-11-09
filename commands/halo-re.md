---
description: "Halo RE: what the pack is, its commands, workflows and lineups -- and its default action"
argument-hint: "[what to do]"
---
This is the Halo RE pack (halo-re 0.5.0): Binary reverse-engineering -- a read-only Ghidra MCP server (decompile,
disassemble, search, xrefs, callgraph), procedural RE skills, kernel-driver and patch-diff audit playbooks, and
triage/analysis/report agent roles.

What it brings:
- command /halo-re:hr-report -- Render confirmed findings into a leadership email or a full report
- lineup halo-re--hr-binary-triage -- Inventory, evidence-checked classification and a ranked verdict for one binary
- lineup halo-re--hr-kernel-driver-audit -- Kernel-driver IOCTL, kernel-API and import-surface auditing
- lineup halo-re--hr-patch-diff -- Comparative analysis of a patch or a CVE pair
- lineup halo-re--hr-semgrep-triage -- Triage the output of a SAST scan over decompiled code
- workflow halo-re/triage -- Triage one binary: inventory, evidence-checked classification, ranked verdict report
- workflow halo-re/semgrep-triage -- Scan decompiled output and triage the rules that fired
- MCP server ghidra -- read-only Ghidra analysis (decompile, disassemble, search, xrefs, imports, callgraph)
- skill halo-re:ghidra-doctor -- find and verify the local Ghidra install, and name the exact fix when it is absent
- skill halo-re:ghidra-mcp-usage -- how to drive the Ghidra MCP server well (token budget, what to ask for)
- skill halo-re:binary-triage, halo-re:kernel-api-audit, halo-re:kernel-driver-ioctl-audit, halo-re:patch-diff-analysis,
  halo-re:semgrep-decompiled, halo-re:macho-triage-diff, halo-re:token-budget-a-binary, halo-re:model-eval-for-re,
  halo-re:re-agent-security -- the procedural know-how behind those playbooks
- skill halo-re:craft-anything-study -- study how any software works, then craft your own version

If the request below is empty, show the user the list above, one line each, and stop. Otherwise: pick the workflow
or lineup that matches the request -- for a single binary start with the workflow `halo-re/triage`, which runs the
Ghidra server read-only and writes one report artifact. Tell the user the command
(`halo workflow run halo-re/triage --input binary=<path>`), what it costs (its budget_usd), and run it once they
agree. Nothing is ever executed: the binary is read, never run. A `lead` is not a finding.

Request: $ARGUMENTS
