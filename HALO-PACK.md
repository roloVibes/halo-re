# HALO-PACK.md: working on the Halo RE pack

You are working in the folder of a Halo pack. Read this page first, then follow its loop for every change. A person
reads it the same way. The full guide is Halo's `docs/PACK-AUTHORING.md`; the contract is `docs/EXTENSION_API.md`.

## What this pack is

`halo-re` (pack.yaml: `id`), "Halo RE": Binary reverse-engineering -- a read-only Ghidra MCP server (decompile,
disassemble, search, xrefs, callgraph), procedural RE skills distilled from agentic-RE training, kernel-driver and
patch-diff audit playbooks, and triage/analysis/report agent roles.

**The repo root IS the pack.** `halo pack sources add https://github.com/roloVibes/halo-re` followed by
`halo pack install halo-re` reads `pack.yaml` at the repo root -- so nothing may be added above it that would break
that (no nested pack folder).

What it brings now (each part one line; pack.yaml lists them under `contributes`):

- bio `halo-re--hr-orchestrator` -- picks the analysis path and owns the finding lifecycle
- bio `halo-re--hr-triage` -- inventory and evidence-checked classification of one binary
- bio `halo-re--hr-analyst` -- the deep pass over a decompiled function or subsystem
- bio `halo-re--hr-vuln-reviewer` -- adversarial read of a candidate: is the evidence decisive?
- bio `halo-re--hr-reporter` -- confirmed-only reporting in the pack's report shape
- command `/halo-re` -- the entry command: what the pack is, its commands, workflows and lineups, and its default action
- command `/halo-re:hr-report` -- leadership email or full report from confirmed findings
- skill `halo-re:ghidra-doctor` -- find and verify the Ghidra install; name the exact fix when it is absent
- skill `halo-re:ghidra-mcp-usage` -- how to drive the Ghidra MCP server well
- skill `halo-re:binary-triage` -- the inventory-first triage procedure
- skill `halo-re:kernel-api-audit` -- kernel-API misuse patterns
- skill `halo-re:kernel-driver-ioctl-audit` -- IOCTL handler auditing
- skill `halo-re:patch-diff-analysis` -- what changed between two builds, and what that implies
- skill `halo-re:semgrep-decompiled` -- SAST over decompiled output (opengrep, not OSS semgrep)
- skill `halo-re:macho-triage-diff` -- Mach-O triage and diffing
- skill `halo-re:token-budget-a-binary` -- size a binary's decompilation before paying for it
- skill `halo-re:model-eval-for-re` -- measure a model on an RE task instead of assuming
- skill `halo-re:re-agent-security` -- what an RE agent must never do with the binary in front of it
- skill `halo-re:craft-anything-study` -- study how any software works, then craft your own version
- lineup `halo-re--hr-binary-triage` -- one binary, inventory to ranked verdict
- lineup `halo-re--hr-kernel-driver-audit` -- kernel-driver IOCTL and import-surface auditing
- lineup `halo-re--hr-patch-diff` -- patch/CVE comparative analysis
- lineup `halo-re--hr-semgrep-triage` -- triage a SAST scan over decompiled code
- workflow `halo-re/triage` -- one binary: inventory, evidence-checked classification, one report artifact
- workflow `halo-re/semgrep-triage` -- scan decompiled output and triage what fired
- MCP server `ghidra` -- read-only Ghidra analysis
- artifact `re-finding-report` -- the report a run writes (confirmed findings, leads kept separate)
- event `re.finding` -- one finding lifecycle moment
- event `re.session` -- a Ghidra analysis session opened, failed or closed
- event `re.craft.study` -- one moment in a craft-anything study
- Studio section `re` -- the findings browser, counts, table and lifecycle feed
- Studio section `craft` -- the craft-studies browser, counts, table and lifecycle feed
- fleet capability `halo-re.analysis` -- runs a binary analysis on a harness that runs the pack

## The contract in one page

- **pack.yaml** is the manifest. `id` is lower-case letters, digits and single hyphens, and is the folder's name.
  `version` is semver. `halo_api: {min: "1.1", max: "1.9"}` is the extension API it is written against.
- **contributes** lists every part. A bio or lineup file that is not listed is a doctor line; a listed file that is
  not there is an install line.
- **The plugin half** lives where a Claude plugin keeps it: `commands/`, `skills/<name>/SKILL.md`,
  `hooks/hooks.json`, `.mcp.json`, `.claude-plugin/plugin.json` (its `name` is the id). Halo reads them in place,
  named `halo-re:<name>`; a hook or a server command uses `${halo_python}` (Halo's own Python) and
  `${CLAUDE_PLUGIN_ROOT}` (this folder).
- **Halo's half**: bios in `agents/*.yaml` (read as `halo-re--<name>`), lineups in `teams/*.yaml`, workflows in
  `workflows/<name>.yaml`, typed events in `events/<kind>.json`, artifact schemas in `artifacts/<name>.json`, Studio
  panels, fleet capabilities, policy hooks and modes, Setup blocks, themes, a `bundle:` block, and the tools it needs
  under `requires:`.
- **`capabilities:`** is the vocabulary everything else gates on: every workflow's
  `prerequisites.capabilities`, every stage's `needs:`, and every `contributes.fleet.capabilities[].name` must be
  one of those names.
- **Code** imports `halo_harness.ext` and nothing else of Halo (`write_private`, `data_dir`, `publish_event`,
  `get_config`, `set_mode`, `testing`, ...).
- **Permissions**: each part that needs one (`hooks`, `mcp:<server>`, `studio-script`, `bash`, `network`,
  `home-write`) is requested in pack.yaml's `permissions`; the owner grants it with
  `halo pack enable halo-re --grant <name>`. Nothing that needs a permission runs until it is granted.

## The loop

```
halo pack test .                          # every check, in a scratch home, no model call, no network
python -m tests.pack_test                 # the same checks plus the pack's own (needs `halo` importable)
~/.venvs/halo-re/bin/python -m pytest tests -q   # the pack's behaviour tests (py3.12 -- never macOS python3)
halo pack doctor                          # the real home: what is missing on THIS machine
halo pack install . --link                # then enable it and start a NEW halo session
```

1. Change the pack. `pack.yaml` is the manifest: every file it names must exist, every permission a part needs must
   be in `permissions:`, and `contributes` is the list of what the pack offers.
2. Run `halo pack test .`. It must print `0 failed`. A `skip` line is a check that needs this machine (a model, a
   tool, a runtime) -- read the reason; a `skip` you cannot explain is a bug in the pack.
3. Run the pack's own tests (`~/.venvs/halo-re/bin/python -m pytest tests -q`).
4. Bump `version` in `pack.yaml` and add the same version to `CHANGELOG.md`. A change the person who runs the pack
   must act on also gets a `migrations` entry, which `halo pack update` prints before it replaces anything.
5. Commit. The GitHub workflow runs `halo pack test .` on Linux and Windows on every push.

## Rules this repo holds to

- **The repo is PUBLIC and ships NO Ghidra, no binaries, no samples.** Ghidra is ~1 GB and is the user's own
  install; the pack ships the MCP server that drives it and the doctor skill that verifies it. Never vendor a
  binary or a decompiled tree into this folder.
- **Nothing is ever executed.** The Ghidra server is read-only and the bios treat a binary as data. A test rejects
  any bio or skill that would run the sample.
- **Never pin a model.** Every bio is `models.preference: default`.
- **The dev venv lives OUTSIDE the pack** (`~/.venvs/halo-re`). A pack folder is scanned and copied whole by
  `halo pack test` / `halo pack install` -- only `.git` and `__pycache__` are skipped -- so a `.venv` inside it is
  copied into the install and trips the privacy scan.
- **Authoring notes stay outside the repo** (`~/halo-re-ops/_research/`). They are not part of the pack and they
  carry personal paths.
- **Harness facts come from GitHub, `roloVibes/Halo-Harness`** (or `halo pack --help` and the installed package),
  never from an assumption about what Halo does.

## Before you share it

`halo pack doctor` clean, `halo pack test .` green, the README true to the files, the permissions the least the
parts use, `CHANGELOG.md` and `version` moved together. Written against Halo 3.3.12.0 and the
[Halo pack template](https://github.com/roloVibes/halo-pack-template).
