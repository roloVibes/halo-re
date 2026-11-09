# Halo RE: what a part needs

One line per part of the pack, and what it needs to run. A harness that does not have a line's requirements skips
that part; nothing here installs anything. `pack.yaml`'s `requires:` carries the install line for each tool.

- `mcp:ghidra` (read-only Ghidra analysis) -- python, `pyghidra`, and a Ghidra install. The pack never bundles
  Ghidra (~1 GB): set `packs.settings.halo-re.ghidra_install_dir`, or let the `ghidra-doctor` skill find it by
  effect. Ghidra project paths must not contain a dot-prefixed element (Ghidra refuses them).
- the five bios and four lineups -- nothing beyond a model. Every bio is `default` (model-agnostic) on purpose.
- `workflows/triage.yaml` -- `mcp:ghidra` (its `prerequisites.grants`), plus the CLI RE tools below.
- `workflows/semgrep-triage.yaml` -- `opengrep` and `ghidrecomp`.
- `skills/semgrep-decompiled`, `skills/kernel-*`, `skills/patch-diff-analysis`, `skills/macho-triage-diff` --
  `opengrep` (not the OSS `semgrep` CLI: it strips the JSON fields a triage model needs), `ghidrecomp`, and the
  usual platform tools (`file`, `nm`, `objdump`/`otool`, `strings`).
- `skills/craft-anything-study` -- `craft-anything-cli`, installed by the user. The skill skips visibly when it is
  absent; the pack never downloads it.
- `tools/findings_store.py`, `tools/findings_view.py`, `tools/craft_studies.py`, `reporting/` -- python standard
  library only.
- `studio/findings.js`, `studio/craft.js` -- the `studio-script` grant.
- `schemas/`, `playbooks/` -- data files, read by the tools and the bios. Nothing to install.
