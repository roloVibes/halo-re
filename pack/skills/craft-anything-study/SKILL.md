---
name: craft-anything-study
description: >-
  Drive the externally-installed craft-anything-cli (a local study engine
  whose ~300 tools are both CLI subcommands and MCP tools) for formats and
  platforms the pack's Ghidra path does not cover: .NET assemblies, Java
  bytecode, Android/APK/Flutter, Apple Mach-O/ObjC/Swift, WASM, firmware,
  game archives, packed executables, and no-Java decompilation when Ghidra
  is absent. Skips visibly when the CLI is not installed.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Craft-Anything Study — broad-format RE via the external study engine

`craft-anything-cli` (github.com/storytold/craft-anything, dual
MIT/Apache-2.0) is a local study engine with roughly 300 tools that are
simultaneously CLI subcommands and MCP tools. It is NOT vendored into this
pack and the pack never downloads it: the user installs it, this skill
drives it over bash. Use it for formats and platforms the pack's Ghidra
path does not cover, and as the decompilation fallback when no Ghidra
install exists.

## Use this skill when
- the target is a .NET assembly — `managed_assembly_show`,
  `managed_ilspy_decompile` — which the Ghidra path handles poorly
- Java bytecode needs reading — `java_class_show`,
  `java_vineflower_decompile`
- an Android APK or Flutter build is in scope — `android_package_show`,
  `android_flutter_identify`
- Apple Mach-O with ObjC/Swift metadata needs structured enumeration —
  `apple_macho_show`, `apple_objc_classes_list`
- WASM modules, firmware images, or game archives (Unity / Unreal /
  Godot) need extraction and inventory
- a packed executable needs unpacking — `core_packed_files_list` then
  `unpack` — covering PyInstaller, .NET single-file, and Bun bundles
- a SQLite database ships with the sample — `db_sqlite_show`
- any unfamiliar target deserves a first-pass inventory —
  `core_target_triage`
- Ghidra is absent or broken and x86/x64/ARM code must still be
  decompiled: craft-anything's built-in engines decompile without Java

## Presence check and visible skip — never a silent failure

Before EVERY use, resolve the CLI: the pack config key
`craft_anything_cli_path` if set, otherwise `command -v
craft-anything-cli`. When it resolves, verify by effect with
`craft-anything-cli doctor`: exit 0 means its self-test of its own MCP
server, engines, and agents passed; a non-zero exit is a failed check —
report the output, do not proceed on hope.

When the CLI is absent, SKIP VISIBLY — print a line like:
`SKIPPED — craft-anything-cli not installed; install it with: cargo
install --path apps/craft-anything-cli (see github.com/storytold/craft-anything
releases), or set packs.settings.halo-re.craft_anything_cli_path` — and
note that the pack's built-in Ghidra path (ghidra-doctor,
ghidra-mcp-usage) remains available. Never degrade silently into doing
nothing and calling it done.

## Install (the user does this; the pack never downloads)

Pinned release: **v0.3.0** — prebuilt from the GitHub releases page:

```sh
curl -fLO https://github.com/storytold/craft-anything/releases/download/v0.3.0/craft-anything-cli-0.3.0-macos-universal.zip
ditto -x -k craft-anything-cli-0.3.0-macos-universal.zip
# put the binary on PATH, e.g. ~/.local/bin
```

Or build from source: `cargo install --path apps/craft-anything-cli`
(Rust 1.97+; the build is heavy). Verify by effect either way:
`craft-anything-cli doctor` must exit 0.

Pin discipline: upstream is alpha (v0.1.0 shipped 2026-10-31); this pack
is validated against v0.3.0. On any upgrade, re-run `doctor` and
re-validate the subcommands this skill names before trusting output.

## Two modes — and the deep-mode guardrail

- **Clean room (default).** Only what a visitor to the artifact could
  see: metadata, structure, public symbols. The engine enforces this
  with a hard gate.
- **Deep (`--deep`).** Reads code and files with built-in engines, plus
  Ghidra when an install exists (discovery order: configured directory,
  engine store, PATH, well-known locations). The flag is per-run and
  NEVER persisted by the CLI — every deep invocation must pass `--deep`
  explicitly.

**Authorized-RE guardrail (binding on you, the agent):** in deep mode
the engine's DRM / copy-protection refusal is PROMPT-LEVEL ONLY — the
hard `clean_room` gate exists only in clean-room mode, so deep mode will
not stop you itself. Regardless of what the tool allows, YOU must refuse
to decrypt, crack, or bypass encryption, copy protection, DRM, or
anti-cheat. This pack is authorized-assessment only: study structure and
behavior on targets you are authorized to assess; refusal here is not a
tool bug to work around.

## Workflow Overview

1. **Presence check** (above). Absent → visible skip, done.
2. **Triage** — `core_target_triage <target>`: first-pass inventory
   (format, platform, packer heuristics). This decides which
   format-specific tools apply; do not guess the format by extension.
3. **Format-specific study** — pick from the coverage list above by
   what triage reported. Unpack first when
   `core_packed_files_list` reports packing (`unpack`, then re-triage
   the unpacked artifacts).
4. **Record** — capture the tool outputs as evidence with the exact
   command lines that produced them; fold anything
   security-relevant into the pack's finding flow (binary-triage
   verdict schema, or a re.finding event for confirmed items).
5. **Hand off** — for PE/ELF/Mach-O code-level questions that
   craft-anything surfaced but did not answer, continue with the
   Ghidra path (ghidra-mcp-usage) when an install exists.

## MCP mode (noted, not registered)

`craft-anything-cli mcp` serves the same tools over stdio JSON-RPC with
toolsets enabled on demand (`list_toolsets`, `enable_toolset`). This is
a future pack integration — today the pack registers only its Ghidra
server, so drive craft-anything through bash. Do not edit the pack's
`.mcp.json` to add it ad hoc.

## Output Schema
```json
{
  "skill": "craft-anything-study",
  "cli": {"resolved_path": "/abs/path/to/craft-anything-cli", "doctor_exit": 0, "version": "0.3.0"},
  "mode": "clean-room | deep",
  "triage": {"format": "dotnet-assembly", "platform": "any", "packed": false},
  "studies": [{"tool": "managed_ilspy_decompile", "target": "/abs/path", "summary": "..."}],
  "evidence": ["command lines + output excerpts"],
  "handoff": {"ghidra_recommended": false, "reason": "fully covered by craft-anything"}
}
```

## When NOT to Use This Skill
- The CLI is not installed and the user does not want to install it —
  take the visible skip and continue with the pack's own path; the pack
  never downloads the CLI on anyone's behalf.
- The target is a plain PE/ELF/Mach-O binary and Ghidra is healthy —
  the pack's Ghidra path is deeper for native code; use craft-anything
  for breadth, not to replace a working Ghidra.
- Anything requiring dynamic execution or network contact — this skill
  is static study only.
- Decryption, cracking, or protection bypass in any form — refused
  regardless of mode, per the guardrail above.
