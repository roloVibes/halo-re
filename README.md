# halo-re

A reverse-engineering capability pack for
[Halo Harness](https://github.com/roloVibes/Halo-Harness): a read-only
Ghidra MCP server, procedural RE skills distilled from agentic-RE training,
kernel-driver and patch-diff audit playbooks, analysis agent roles, and
triage/static-sweep workflows.

## Installation

Five steps; the pack itself takes under a minute, Ghidra (step 4) is the
only big download. Every command below was run and verified against
halo 3.3.4.0.

### Before you start

- **[Halo Harness](https://github.com/roloVibes/Halo-Harness) 3.2.0.0 or
  newer, already installed and initialized.** This is a Halo pack, not a
  standalone program — without Halo there is nothing to install it into.
  If you don't have Halo yet:

  ```sh
  curl -fsSL https://raw.githubusercontent.com/roloVibes/Halo-Harness/master/scripts/install-halo.sh | bash
  halo init        # the wizard: provider, model, permission mode
  ```

  (Windows and no-installer options:
  [Halo-Harness docs/INSTALL.md](https://github.com/roloVibes/Halo-Harness/blob/master/docs/INSTALL.md))

- **git**, to clone this repo.
- For binary analysis (step 4): **Ghidra** (~570 MB, Apache-2.0 — not
  bundled) and a **JDK 21+**. The pack's doctor can download Ghidra for
  you; everything else it detects automatically.

### Step 1 — clone this repo (location is your choice)

```sh
git clone https://github.com/roloVibes/halo-re.git ~/src/halo-re
```

`~/src/halo-re` is just an example — the clone can live anywhere.
The clone is only the **download source**: step 2 copies the pack into
Halo's own storage (`~/.halo/packs/halo-re/`), and after that the
clone is no longer needed.

> **Do not** use `halo pack install
> https://github.com/roloVibes/halo-re.git` — it fails with
> `no pack.yaml in src`. Halo requires the pack manifest at the root of
> a git URL, and this repo keeps it under `pack/`. Install from the
> cloned folder's `pack/` subdirectory, as in step 2.

### Step 2 — install the pack

Run this in your **terminal** — the same place you run `halo`. You do
not need a Halo session open; if you run it through a session's shell
tool that works too, but the pack only loads in sessions started
*after* step 3 (Halo reads enabled packs when a session starts).

```sh
cd ~/src/halo-re                # wherever you cloned it
halo pack install ./pack
```

Expected output:

```
installed halo-re 0.2.1 at ~/.halo/packs/halo-re (disabled)
it offers: 5 bios, 4 lineups, 11 skills, 1 MCP server
it requests: mcp:ghidra, bash
enable it: halo pack enable halo-re --grant mcp:ghidra --grant bash
```

The pack arrives **disabled** — that is normal; step 3 turns it on.
(If you see `halo-re is already installed ... (halo pack update
halo-re)`, you already did this — continue at step 3.)

### Step 3 — enable it and grant what it needs

```sh
halo pack enable halo-re --grant mcp:ghidra --grant bash
```

(`mcp:ghidra` is the read-only Ghidra server; `bash` is what the
skills and playbooks run under.)

### Step 4 — set up Ghidra (the doctor does the work)

Start a new Halo session (`halo`) — a session that was already open
when you enabled the pack will not have it — and run the pack's
`halo-re:ghidra-doctor` skill once. It:

- finds an existing Ghidra install (or offers to download the latest
  official release — it picks one with natives for your OS, a release
  that ships none is rejected automatically),
- checks the JDK (21+), fixes the exec bits release zips lose, and
  verifies the install **by effect** (running it, not `which`),
- persists the path (`halo config set packs.settings.halo-re.ghidra_install_dir <path>`)
  so the pack always knows where it is,
- names the exact `pyghidra` install command for the Python Halo runs
  under — run that one command; without it the server starts but
  binary analysis refuses.

### Step 5 — verify

```sh
halo pack list              # → halo-re  0.2.1  enabled  user
halo pack inspect halo-re   # → state: enabled; mcp:ghidra (granted), bash (granted); problems: none
```

Then, in a Halo session:

```sh
halo teams use halo-re--hr-binary-triage
```

or run a workflow headless:

```sh
halo workflow run halo-re/triage --input binary=<path-to-binary>
```

### Updating and removing

```sh
git -C ~/src/halo-re pull     # refresh the clone first
halo pack update halo-re      # shows what changes, asks before applying
halo pack remove halo-re      # the pack's files only; your config stays
```

Note: a Halo upgrade reinstalls its Python environment — `pyghidra`
must be reinstalled there (the doctor names the command) or the server
starts but binary analysis refuses.

## The design rule

**Binary analysis without giving the agent a write primitive.** Every
tool the pack contributes is read-only by construction — no rename, no
delete, no save exists in the surface — so the agent can decompile,
cross-reference, and diff a binary without any way to alter the analysis
project or the target.

## What it adds to Halo

| Piece | What it is |
|---|---|
| **Ghidra MCP server** (`pack/mcp/`) | stdio server over pyghidra: `decompile_function`, `disassemble`, `search_functions`, `search_strings`, `list_imports`/`list_exports`, `list_xrefs`, `gen_callgraph`, `read_bytes`, `binary_metadata`, `list_binaries`, `open_binary`. Read-only by construction: no rename/delete/save tools exist. |
| **11 skills** (`pack/skills/`) | Procedural know-how: Ghidra bring-up and usage, binary triage, token budgeting, kernel IOCTL audit, kernel API audit, patch-diff analysis, Mach-O triage/diff, semgrep-on-decompiled, agent security posture, model evaluation for RE. |
| **5 agent roles + 4 lineups** | orchestrator, triage, analyst (drives the Ghidra tools), vuln-reviewer (read-only judge), reporter; lineups for triage, kernel-driver audit, patch diff, semgrep triage. |
| **8 playbooks** | Structured workflows with impact classes and evidence requirements — all read-only/low-impact toward the world. |
| **2 Halo workflows** | `halo workflow run halo-re/triage --input binary=<path>` and `halo-re/semgrep-triage` — multi-stage, judged, gated pipelines that compile to Orchestra goals. |
| **Artifacts + events** | The `re-finding-report` artifact schema and `re.finding` / `re.session` events for the Studio live feed. |

## What you supply — never bundled

Ghidra is ~570 MB and licensed Apache-2.0 — the pack does not ship it.
The details behind [Installation](#installation) step 4:

- the doctor detects by effect (no `which ghidra` — there is no such
  binary) and auto-detects existing installs by globbing
  `ghidra_*_PUBLIC` under `~/Documents`, `~/Downloads`, `~` and the
  tools dir;
- the on-demand installer downloads from
  github.com/NationalSecurityAgency/ghidra/releases, extracts into the
  tools dir (default `~/halo-re-tools`, config key `tools_dir`), and a
  release that ships no natives for your OS (measured: Ghidra 12.2+
  dropped the macOS decompiler) is rejected with the previous release
  tried automatically;
- the same installer handles the optional **REA** (Reverse Engineer
  Anything) release: `install_tools.py --tool rea --yes` (~98 MB, MIT,
  Windows exe);
- Python dep for the MCP server: `pyghidra` in the Python Halo runs
  under (the doctor names the exact command). No MCP SDK pin — the
  server imports `FastMCP` (mcp 1.x) or `MCPServer` (mcp 2.x), whichever
  the environment has.

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

0.2.1 — `halo pack inspect` reports `problems: none` (validated against
halo 3.2.1.0 and, on 2026-10-27, halo 3.3.2.0). The MCP server is
smoke-tested end-to-end against a real Ghidra 12.1.2 install (decompile
through stdio JSON-RPC, all 12 tools); the mcp 1.x→2.x SDK rename
(`FastMCP` → `MCPServer`) is handled at import, initialize + tools/list
verified under Halo's Python. Note a Halo upgrade reinstalls its Python
env — `pyghidra` must be reinstalled there (the doctor names the
command) or the server starts but binary analysis refuses. See
[pack/COMPATIBILITY.md](pack/COMPATIBILITY.md).

## License

Copyright © 2026 **Pinball Genie LLC**. All rights reserved — no
open-source reuse rights are granted. See `/LICENSE`. Pinball Genie LLC
is the holding entity for all of roloVibes' development projects.

---

# Technical documentation

*The sections below are the substance behind the pitch above: how the
pieces actually work, with the real code paths.*

## How an analysis runs

```
you ──install pack──▶ Halo ──grant mcp:ghidra──▶ the read-only tool surface
                                                     │
a binary ──open_binary──▶ Ghidra project (import + analyze, expensive, once)
                                                     │
        triage ──▶ search/decompile/xrefs/callgraph ──▶ candidate findings
                                                     │
                            vuln-reviewer (read-only judge) ──▶ report
```

1. [Install the pack](#installation) (clone → `halo pack install ./pack`
   → `halo pack enable halo-re --grant mcp:ghidra --grant bash`), and run
   the `halo-re:ghidra-doctor` skill once: it finds (or downloads) the
   Ghidra install, verifies it by effect, and persists the path.
2. `open_binary <path>` imports and analyzes the target — expensive, done
   once per binary; every later tool call reads from the same session.
3. The triage lineup (`halo teams use halo-re--hr-binary-triage`) drives
   the tools: platform/arch classification, then decompile/xref/callgraph
   on the interesting functions.
4. Candidates go to the vuln-reviewer — a read-only judge — and land in
   the `re-finding-report` artifact schema with the `re.finding` event
   for the Studio live feed.

## The MCP server

`pack/mcp/ghidra_server.py` is a stdio JSON-RPC server over the pyghidra
core (`pack/mcp/ghidra_core.py`), launched by `.mcp.json` under Halo's
own Python (`${halo_python}` / `${CLAUDE_PLUGIN_ROOT}`). It speaks both
mcp 1.x (`FastMCP`) and 2.x (`MCPServer`); without `pyghidra` it starts
and every tool degrades to a doctor-pointing error instead of crashing.
Config keys: `ghidra_install_dir`, `project_dir` (never dot-prefixed —
Ghidra refuses it), `tools_dir`, `rea_dir`.

Every measured trap — dot-prefixed project paths, GHIDRA_INSTALL_DIR
inheritance, the fresh-import analysis gap, the two-stage start, the zip
exec-bit loss — is in
[pack/docs/GHIDRA-NOTES.md](pack/docs/GHIDRA-NOTES.md) and baked into the
code.

---

**Halo Harness runs the agents. halo-re gives them binary analysis worth
running.**
