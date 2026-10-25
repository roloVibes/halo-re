---
name: ghidra-doctor
description: >-
  Verify a Ghidra installation by effect (version file parses, headless
  analyzer exists, native decompiler exists for this platform) plus the
  Python deps the pack's MCP server needs, ending in a live decompilation
  smoke test. Run it whenever a halo-re ghidra tool answers "no usable
  Ghidra install" or the session fails to open, before suspecting the
  tools or the model.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Ghidra Doctor — verify the install by effect

Procedural preflight for the halo-re Ghidra toolchain. Ghidra ships no
`ghidra` binary — a zip-extract install puts nothing on PATH — so presence
is proven only by the artifacts that matter: the version file, the headless
analyzer, and the platform-specific native decompiler. The doctor resolves
the install, validates the project directory, checks the Python
dependencies, and finishes by decompiling one real function through the
pack's own MCP server (tools surface in a Halo session under the
`halo-re_ghidra` prefix, served by the MCP server named `ghidra`).

## Use this skill when
- any halo-re ghidra tool returns an error mentioning "no usable Ghidra
  install", "pyghidra is not importable", or "the Ghidra session is not
  running"
- bringing up halo-re on a machine for the first time, or after a Ghidra
  upgrade/move
- a Ghidra project open fails with `IllegalArgumentException` about path
  elements (dot-prefixed project dir — see step 5)
- before a long analysis run, so a broken environment fails in seconds
  instead of mid-engagement

## Workflow Overview

1. **Resolve the install — in this exact order** (matches
   `ghidra_core.detect_install`): (a) the pack config key
   `halo pack config halo-re ghidra_install_dir <path>`, (b) the
   `GHIDRA_INSTALL_DIR` environment variable, (c) common system locations
   (`/ghidra`, `/opt/ghidra`, `/usr/share/ghidra`, `C:/Program Files/ghidra`),
   then (d) a glob for `ghidra_*_PUBLIC` directories up to three levels under
   `~/Documents`, `~/Downloads` and `~` (zip-extract installs live wherever
   the user unpacked them). If a candidate fails, collect *why* and move
   to the next; the final error must list every candidate it tried.
2. **Verify by effect, never by `which ghidra`** (no such binary exists).
   For the resolved root, assert all three:
   - `<root>/Ghidra/application.properties` is a file and parses (read the
     `application.version=` line — that value is the verified version);
   - `<root>/support/analyzeHeadless` is a file;
   - `<root>/Ghidra/Features/Decompiler/os/<plat>/decompile` is a file,
     where `<plat>` is `mac_arm_64` / `mac_x86_64` / `win_x86_64` / `win_x86`
     / `linux_arm64` / `linux_x86_64` for this host. A decompiler native
     for a *different* platform is a failed check.
3. **If no candidate passes, OFFER THE DOWNLOAD** — the pack can install
   the official release on demand. Ask the user first (it is ~570 MB):
   "No Ghidra install found. Download the latest official release
   (Ghidra 12.x, ~570 MB) into ~/halo-re-tools?" When they say yes, run
   `${CLAUDE_SKILL_DIR}/scripts/install_tools.py --tool ghidra --yes`
   (run with `--check` first to show the exact version/size without
   downloading). The script downloads from
   github.com/NationalSecurityAgency/ghidra/releases, extracts into the
   tools dir (config key `tools_dir`, default `~/halo-re-tools`), verifies
   the install BY EFFECT, and persists the path itself:
   `halo config set packs.settings.halo-re.ghidra_install_dir <path>`.
   It also checks `java -version` (Ghidra needs JDK 21+; Temurin:
   https://adoptium.net) and names the remedy when the JDK is missing or
   old. The optional REA tool (Reverse Engineer Anything,
   github.com/ReverseEngineer-Anything/REA-Github) installs the same way:
   `--tool rea --yes` (~40 MB, MIT); its path lands in `rea_dir`.
4. **If the user declines the download**, set the path by hand to an
   install they already have:
   `halo config set packs.settings.halo-re.ghidra_install_dir <path>`
   (the `GHIDRA_INSTALL_DIR` env var works for one-off runs, but config
   survives across sessions). Do not export `GHIDRA_INSTALL_DIR`
   mid-session expecting the running server to pick it up — it must be set
   before `pyghidra.start()`, i.e. before the session opens; restart the
   session after changing it.
5. **Check the Python deps** with `python -c "import pyghidra, mcp"`.
   Exit code 0 = pass. On failure, install into the *same Python Halo
   runs the pack with* (match `sys.executable`): 
   `python -m pip install pyghidra "mcp>=1.2,<2"`. The `mcp<2` pin is
   deliberate — newer majors break the FastMCP import the server uses.
6. **Validate the project dir**: it must not contain any dot-prefixed
   path element — Ghidra throws
   `IllegalArgumentException: Path element starting with '.' is not
   permitted`, which is why projects never live under `~/.local/share`
   or `~/.halo`. Default (and correct fallback): `~/ghidra-projects`.
   Override with the pack config key `project_dir`.
7. **Grant the tools** if not already granted:
   `halo pack enable halo-re --grant mcp:ghidra`.
8. **Smoke test through the real server**: call `list_binaries` (expect
   `status: ok`, even with an empty list), then
   `open_binary` with a small known-good binary such as `/bin/ls` (first
   open runs full analysis, ~1 min), then `decompile_function` with
   `main`. A pass is a returned `code` field containing C — not merely
   the absence of an error.
9. **Report** the verdict as the JSON below, including every check's
   literal result (path, version string, exit code) — not a bare "OK".

Verification table — don't assume, assert instead:

| Check | Don't assume | Assert instead |
|---|---|---|
| Ghidra installed | `which ghidra` output | `Ghidra/application.properties` parses; version line read |
| Headless analyzer | "the folder looks like Ghidra" | `support/analyzeHeadless` is a file |
| Native decompiler | it worked before / on another machine | `Decompiler/os/<this-platform>/decompile` is a file |
| Python deps | `pip list` shows the names | `python -c "import pyghidra, mcp"` exits 0 |
| Server usable | tools are connected | `list_binaries` returns `status: ok` |
| End-to-end | server starts | `decompile_function("main")` on `/bin/ls` returns C code |

## Output Schema
```json
{
  "skill": "ghidra-doctor",
  "verdict": "healthy | fixed | broken",
  "ghidra": {
    "install_dir": "/abs/path",
    "version": "12.1.2",
    "resolved_via": "pack-config | env | common-location",
    "verified_by": ["application.properties", "support/analyzeHeadless", "Decompiler/os/mac_arm_64/decompile"]
  },
  "project_dir": "~/ghidra-projects",
  "project_dir_valid": true,
  "deps": {"pyghidra": true, "mcp_pinned": ">=1.2,<2", "import_check_exit_code": 0},
  "smoke_test": {"binary": "/bin/ls", "function": "main", "decompiled": true},
  "fixes_applied": ["set ghidra_install_dir via halo pack config"],
  "remaining_problems": []
}
```

## When NOT to Use This Skill
- The ghidra tools already answer with real data — the doctor adds nothing
  and re-opening `/bin/ls` costs a full analysis cycle.
- Deciding *which* Ghidra version to install or licensing questions — this
  skill verifies, it does not procure; Ghidra is never bundled with the pack.
- As a workaround for a dot-prefixed project path (symlinks, renames) —
  fix the `project_dir` config key instead; the constraint is on every
  path element, not just the leaf.
- Tuning decompilation quality or model selection — the doctor proves the
  pipeline runs; it says nothing about analysis depth.
