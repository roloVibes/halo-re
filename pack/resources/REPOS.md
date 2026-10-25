# REPOS.md — the reverse-engineering ecosystem this pack draws on

Curated from the GitHub topic page
https://github.com/topics/reverse-engineer-anything (checked 2026-10-25)
and the tools the pack's skills reference.

## The REA (Reverse Engineer Anything) ecosystem

The topic is centered on **REA** — a methodology (and local MCP agent tool)
where AI agents reverse-engineer real things and rebuild them. Its flagship
tool repo hooks the classic RE disassemblers over MCP, the same shape as
this pack's Ghidra server:

- **ReverseEngineer-Anything/REA-Github** — https://github.com/ReverseEngineer-Anything/REA-Github
  REA 6.3.0: local MCP agent with Hopper, Ghidra and IDA hooks; streaming
  JSON; Electron/browser paths; MIT-licensed, zip-release. Same-machine
  only ("Cloud? No. MCP stays on the box") — the same local-first posture
  this pack takes.
- **AIshihzong/awesome-reverse-engineer-anything** — https://github.com/AIshihzong/awesome-reverse-engineer-anything
  The topic's most-starred repo (173★): awesome list of AI RE case studies
  — what agents took apart and recreated, and which really used REA.
- **git-sanbu/awesome-rea** — https://github.com/git-sanbu/awesome-rea
  Source-backed REA case studies (games, apps, hardware, tool
  integrations), 12 language editions.
- **jammyfu/rea-atlas** — https://github.com/jammyfu/rea-atlas
  Map of RE projects tagged by whether they used REA (Yes/No/Unverified):
  game decomp/recomp, re-implementations, asset tools, firmware, protocol.
- **sickpyramid/ReaFuse** — https://github.com/sickpyramid/ReaFuse
  Dissect two projects, fuse their capabilities into a new verified one.
- **glauberlima/open-scrantic** — https://github.com/glauberlima/open-scrantic
  Clean-room Rust reimplementation of the Johnny Castaway screensaver — a
  worked example of agent-driven RE of legacy software.

## Core tools this pack uses

- **Ghidra** — https://github.com/NationalSecurityAgency/ghidra (Apache-2.0).
  Driven through pyghidra; never bundled with the pack (see the
  ghidra-doctor skill).
- **pyghidra** — https://github.com/NationalSecurityAgency/ghidra/tree/master/Ghidra/Features/PyGhidra
  The Python bridge the pack's MCP server runs on.
- **ghidriff** — https://github.com/clearbluejar/ghidriff — patch diffing
  (VersionTrackingDiff) with the similarity field the diff playbooks triage on.
- **ghidrecomp** — https://github.com/clearbluejar/ghidrecomp — decompile
  every function to its own .c file (the semgrep sweep's input).
- **pyghidra-mcp** — https://github.com/clearbluejar/pyghidra-mcp — the
  reference MCP server this pack's server follows the architecture of.
- **opengrep** — https://github.com/opengrep/opengrep — OSS Semgrep fork
  that keeps `extra.lines`/`extra.metavars` in JSON output (OSS semgrep
  redacts them; any LLM-triage pipeline must use opengrep).
- **0xdea semgrep-rules** — https://github.com/0xdea/semgrep-rules — the
  community C rules the static sweep runs.
- **LIEF** — https://github.com/lief-project/LIEF and
  **Capstone** — https://www.capstone-engine.org — the Mach-O triage-diff
  path that avoids a 40-minute Ghidra import.
- **GhidraMCP** — https://github.com/LaurieWired/GhidraMCP — the GUI-plugin
  MCP route (HTTP :8080 + bridge) when live CodeBrowser annotation is
  wanted; the pack's headless server covers the rest.

## Skills spec

- **agentskills.io** — https://agentskills.io — the open SKILL.md format
  the pack's skills follow (frontmatter + workflow + output schema +
  when-not-to-use).
