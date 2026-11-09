# Changelog: Halo RE (halo-re)

Each release of the pack, newest first: the version (pack.yaml's `version`), the date, what changed for the person
who runs it. A change they must act on also gets a `migrations` entry in pack.yaml, which `halo pack update` prints
before it replaces anything.

## 0.5.0 - 2026-11-08

**Framework conformance.** The pack now uses the Halo pack template
(https://github.com/roloVibes/halo-pack-template) end to end. **Action required: reinstall.**

- **The repo root is now the pack.** The installable unit moved from `pack/` to the repository root, so
  `halo pack sources add https://github.com/roloVibes/halo-re` + `halo pack install halo-re` works. An existing
  install recorded from `./halo-re/pack` must be updated or reinstalled once.
- `pack.yaml`: `halo_api` is now a `{min, max}` range (1.1 - 1.9) and `halo.min` is `3.3`; `capabilities` lists the
  pack's fleet capability; `contributes.fleet` declares `halo-re.analysis`; `contributes.commands` is declared.
  Everything else the pack contributes is unchanged.
- `requires:` now names the external tools the pack drives, each with the install line, url and license:
  `pyghidra` (the Ghidra bridge, Apache-2.0), `opengrep` (LGPL-2.1 -- the OSS `semgrep` CLI strips the JSON fields a
  triage model needs), `ghidrecomp` (GPL-3.0) and `craft-anything-cli` (MIT/Apache-2.0). Halo never installs them;
  `halo pack doctor` names a missing one and `halo pack test` skips what it gates.
- The template's project files are in place: `HALO-PACK.md`, `CHANGELOG.md`, `tests/` (the pack's own test entry
  plus the samples its event and artifact schemas are exercised against), `.claude-plugin/plugin.json`,
  `.gitattributes`, and `.github/workflows/pack-test.yml` (`halo pack test .` on Linux and Windows per push).
- `/halo-re` entry command added -- what the pack is, its commands, workflows and lineups, and its default action.
- `fleet/notes.md` -- one line per part and what it needs on the harness that runs it.
- The pack's own test entry (`python -m tests.pack_test`) is new; the existing `tests/test_pack.py` behaviour suite
  is unchanged and still green.

## 0.4.0 - 2026-10-29

- Two Studio sections: `re` (findings browser, counts, table, lifecycle feed) and `craft` (craft-studies browser
  and tables).

## 0.3.0 - 2026-10-25

- Findings lifecycle, reporting (leadership email + full report, confirmed only), the Studio findings browser, and
  the craft-anything study path.

## 0.2.0 - 2026-10-25

- Kernel-driver and patch-diff audit playbooks, the semgrep-decompiled skill, and the `triage` /
  `semgrep-triage` workflows.

## 0.1.0 - 2026-10-25

- First version: the read-only Ghidra MCP server, the `ghidra-doctor` skill, five bios and four lineups.
