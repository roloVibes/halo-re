# COMPATIBILITY.md — supported Halo versions and API requirements

## Current status

| Halo version | Support | Path |
|---|---|---|
| 3.2.0.0+ (pack program, RELEASED, shipped through 3.2.1.0) | Native target | `halo pack install <this-dir>` — validated 2026-10-25 against halo 3.2.1.0: `problems: none`, installs clean, 5 bios + 4 lineups + 11 skills + 1 MCP server + 2 workflows offered |
| Below 3.2.0.0 | Not supported | No compat adapter (unlike halo-hacker): the pack's value is mostly the MCP server + workflows, which do not exist before 3.2.0.0 |

## Interfaces the pack depends on (verified 2026-10-25 against halo 3.2.1.0 @ a7b2c15)

| Interface | Where | Status | Pack use |
|---|---|---|---|
| Agent bio YAML grammar | `halo_harness/agents_yaml.py` | stable | `agents/*.yaml` — pinned by `tests/test_pack.py::test_bios_pass_the_real_harness_validator` |
| Team template grammar | `halo_harness/teams_yaml.py` | stable | `teams/*.yaml` — same pin |
| Plugin layout (skills, `.mcp.json`) | `docs/EXTENSION_API.md` "Skills, commands, hooks and MCP" | stable (3.2.0.0 R1) | skills load as `halo-re:<skill>`; the MCP server starts only with the `mcp:ghidra` grant |
| `${halo_python}` / `${CLAUDE_PLUGIN_ROOT}` | `halo_harness/packs/interpreter.py` | stable (R7) | `.mcp.json` launches the server under Halo's own Python |
| Extension API | `halo_harness.ext` | stable at 1.0 | `get_config` (ghidra_install_dir, project_dir), `publish_event` (re.finding, re.session) |
| Workflows | `halo_harness/packs/workflow_rules.py` | stable (R5) | `workflows/triage.yaml`, `workflows/semgrep-triage.yaml` |
| Artifacts | `contributes.artifacts` | stable (R5) | `artifacts/re-finding-report.json` |

## Hard rules

- The pack imports `halo_harness` ONLY through `halo_harness.ext` (the
  documented contract); the MCP server degrades gracefully standalone
  (tests, manual runs) without it.
- The MCP server never bundles or downloads Ghidra; it drives an install
  the user owns and the doctor verifies.
- `mcp` is pinned `<2` (a measured stack constraint shared with the
  pyghidra tooling generation).
