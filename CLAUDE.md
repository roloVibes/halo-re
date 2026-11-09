# CLAUDE.md — halo-re dev context

You are working in the **halo-re repo** — the public, distributable
reverse-engineering capability pack for
[Halo Harness](https://github.com/roloVibes/Halo-Harness): a read-only Ghidra
MCP server plus procedural RE skills. Launch `halo` here to develop the pack.

**Read `HALO-PACK.md` first** — it is the pack's own contract page (what the
pack is, the change loop, the rules). This file only adds repo-specific notes.

## The layout (pack at the repo root)

The repo root **is** the installable pack, so `halo pack sources add
https://github.com/roloVibes/halo-re` + `halo pack install halo-re` works. Do
not introduce a nested pack folder.

```
vibes/appDev/halo-re/          the pack (pack.yaml, agents/, skills/, mcp/, ...)
~/.venvs/halo-re/              the dev venv — OUTSIDE the pack, on purpose
~/halo-re-ops/_research/       private authoring notes — OUTSIDE the pack, on purpose
```

A pack folder is scanned and copied whole by `halo pack test` / `halo pack
install` (only `.git` and `__pycache__` are skipped). Anything cache-shaped or
private inside it — a venv, a research tree, a decompiled sample — is copied
into the install and trips the privacy scan. Keep them out.

## The dev loop

```
halo pack test .                                  # must stay 0 failed (skips are fine, read them)
~/.venvs/halo-re/bin/python -m pytest tests -q    # the behaviour suite (py3.12 — never macOS python3)
halo pack inspect .                               # must stay: problems: none
halo pack update halo-re                          # run from vibes/appDev (the recorded source's parent)
start a NEW halo session                          # packs load at session start, never mid-session
```

- The installed pack's recorded source is **relative** (`./halo-re`): run
  `halo pack` commands from the directory holding the pack repos
  (`vibes/appDev`). It used to be `./halo-re/pack` — reinstall once after the
  root move.
- `halo pack doctor` is the machine's own truth: it names a missing
  requirement (`pyghidra`, `opengrep`, `ghidrecomp`, `craft-anything-cli`) with
  the install line for this OS.
- Ghidra doctor: run the `halo-re:ghidra-doctor` skill in a session after
  enabling; it names the exact `pyghidra` command for halo's Python.

## Where truth lives

**Harness facts → GitHub, `roloVibes/Halo-Harness`** (fetch + read
`origin/master:...`, or `gh`), or the installed package
(`~/.local/share/uv/tools/halo-harness/lib/*/site-packages/halo_harness/`) —
`packs/manifest.py`, `packs/typed.py`, `packs/studio_rules.py`,
`packs/fleet_rules.py` and `schemas/pack_yaml.py` are the contract. NEVER the
`appDev/Halo-Harness` folder — the PC's dev workspace, a partial snapshot; do
not modify or delete it.

## Never-do list

- No personal paths in the repo; it is PUBLIC. Use `~/...`, never an absolute
  home path — the privacy scan flags those and `halo pack test` fails on them.
- `_research/` and the venv stay outside the pack (see the layout above).
- Ghidra stack traps (measured): no binary named `ghidra` (detect by effect),
  no dot-prefixed project paths, pin `mcp<2` where MCPO is used,
  `shouldAskToAnalyze=False` on fresh imports.
- Never `halo pack install --project` for an id already installed user-scope —
  it clobbers the user state record.
- Never vendor a binary, a Ghidra release, or a decompiled tree into this repo.

## Sub-agent model rules (standing)

Quality-critical sub-agent work: an explicit Claude model
(`or:anthropic/claude-opus-4.8` / `-5`) or `or:z-ai/glm-5.3-flash`.
Vision (frames/screenshots) → an Opus model. Local LAN models: not trusted for
quality-critical work.
