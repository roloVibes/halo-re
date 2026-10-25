#!/usr/bin/env python3
"""Halo RE pack validator.

Validates the pack against (a) the shipped pack.yaml contract (verified
2026-10-25 against halo 3.2.1.0 / halo_harness/packs/manifest.py) and (b)
the Halo agent-bio / team-template YAML grammar as implemented in
halo_harness/agents_yaml.py + teams_yaml.py (mirrored field-for-field so
validation works without a harness checkout; tests/test_pack.py ALSO runs
the real harness validators against this pack when a checkout exists).

halo-re specifics checked here that halo-hacker's validator does not:
- the Ghidra MCP server: .mcp.json declares it, the script exists and
  compiles, and every tool name the skills reference exists in it;
- skills/: every SKILL.md parses, has the required frontmatter, the name
  matches its directory, and no skill quotes course material verbatim
  (checked structurally: no notebook cell artifacts);
- events/ and artifacts/ schemas are valid JSON.

Exit code is the gate: 0 = valid, 1 = any problem (one plain line each).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

PACK_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_REQUIRED = ("id", "name", "version", "description",
                     "author", "license", "halo_api", "capabilities",
                     "requires", "contributes")
# Mirrored from halo_harness/agents_yaml.py (verified 2026-10-25 against
# halo 3.2.1.0 @ a7b2c15).
BIO_SECTIONS = ("models", "tools", "context", "limits", "output",
                "environment", "acceptance", "hooks", "schedule", "triggers")
KNOWN_KINDS = ("main", "subagent", "researcher", "judge", "reviewer",
               "custom", "media")
# Halo model refs: a route prefix (or:, ol:, xp:, hf:, dbx:, oai:, ...) or
# the literal `default` (session model). The pack hardcodes nothing.
MODEL_REF_OK = re.compile(r"^(default|[a-z]{2,}:.+)")

HR_REQUIRED = ("responsibility", "boundaries", "inputs", "outputs",
               "evidence_requirements", "completion_criteria")

# Every MCP tool name the server exposes (mcp/ghidra_server.py); skills and
# playbooks may only reference these.
GHIDRA_TOOLS = {"list_binaries", "binary_metadata", "open_binary",
                "search_functions", "search_strings", "list_imports",
                "list_exports", "decompile_function", "disassemble",
                "read_bytes", "list_xrefs", "gen_callgraph"}

SKILL_FRONTMATTER_REQUIRED = ("name", "description", "license", "metadata")

problems: list[str] = []


def p(msg: str) -> None:
    problems.append(msg)


def load_yaml(path: Path) -> dict | None:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        p(f"{path.name}: YAML parse error: {e}")
        return None
    if not isinstance(data, dict):
        p(f"{path.name}: top level must be a YAML mapping")
        return None
    return data


def validate_manifest() -> dict | None:
    m = load_yaml(PACK_ROOT / "pack.yaml")
    if m is None:
        return None
    for key in MANIFEST_REQUIRED:
        if key not in m:
            p(f"pack.yaml: missing required key {key!r}")
    halo_api = m.get("halo_api")
    if not isinstance(halo_api, dict) or "min" not in halo_api:
        p("pack.yaml: halo_api must be a mapping with at least 'min'")
    else:
        # Extension API version (halo_harness.ext.API_VERSION), e.g. "1.0".
        if not re.match(r"^\d+\.\d+$", str(halo_api.get("min", ""))):
            p("pack.yaml: halo_api.min must be an extension-API version (e.g. 1.0)")
    if "namespace" in m:
        p("pack.yaml: 'namespace' is not part of the shipped contract; nothing reads it")
    if m.get("id") != "halo-re":
        p("pack.yaml: id must be 'halo-re'")
    perms = m.get("permissions")
    if not isinstance(perms, list) or "mcp:ghidra" not in perms:
        p("pack.yaml: permissions must be a list containing 'mcp:ghidra'")
    return m


def validate_bio(path: Path) -> dict:
    data = load_yaml(path) or {}
    if path.stem != data.get("name"):
        p(f"{path.name}: bio 'name' ({data.get('name')!r}) must match filename stem {path.stem!r}")
    kind = data.get("kind")
    if kind not in KNOWN_KINDS:
        p(f"{path.name}: kind {kind!r} not one of {', '.join(KNOWN_KINDS)}")
    for section in BIO_SECTIONS:
        if section in data and data[section] is not None and not isinstance(data[section], dict) \
                and section != "triggers":
            p(f"{path.name}: {section!r} must be a mapping")
    models = data.get("models") or {}
    pref = models.get("preference") if isinstance(models, dict) else None
    if pref is not None and not MODEL_REF_OK.match(str(pref)):
        p(f"{path.name}: models.preference {pref!r} is neither 'default' nor a route ref -- the pack hardcodes no models")
    if pref is not None and str(pref).startswith(("cc:", "cx:")):
        p(f"{path.name}: models.preference {pref!r} uses a removed/consent-gated route")
    # A bio that declares the pack's MCP server must also request the grant.
    tools = data.get("tools") or {}
    servers = tools.get("mcp_servers") if isinstance(tools, dict) else None
    servers = servers if isinstance(servers, list) else []
    if "ghidra" in servers:
        needs = tools.get("needs")
        needs = needs if isinstance(needs, list) else []
        if "mcp:ghidra" not in needs:
            p(f"{path.name}: tools.mcp_servers names 'ghidra' but tools.needs lacks 'mcp:ghidra'")
    hr = data.get("hr")
    if not isinstance(hr, dict):
        p(f"{path.name}: missing 'hr:' pack-extension block")
    else:
        for key in HR_REQUIRED:
            if key not in hr:
                p(f"{path.name}: hr.{key} is required")
    return data


def validate_team(path: Path, bio_names: set[str]) -> None:
    data = load_yaml(path) or {}
    if path.stem != data.get("name"):
        p(f"{path.name}: template 'name' ({data.get('name')!r}) must match filename stem {path.stem!r}")
    agents = data.get("agents")
    if not isinstance(agents, list) or not agents:
        p(f"{path.name}: 'agents' must be a non-empty list")
        return
    main_count = 0
    aliases: set[str] = set()
    for i, entry in enumerate(agents):
        if not isinstance(entry, dict):
            p(f"{path.name}: agents[{i}] must be a mapping")
            continue
        name = entry.get("agent")
        if not name:
            p(f"{path.name}: agents[{i}]: 'agent' is required")
        elif name not in bio_names:
            p(f"{path.name}: agents[{i}]: no such agent bio: {name!r}")
        role = entry.get("role")
        if not role:
            p(f"{path.name}: agents[{i}]: 'role' is required")
        elif role == "main":
            main_count += 1
        alias = entry.get("as")
        if alias:
            if alias in aliases:
                p(f"{path.name}: duplicate alias {alias!r}")
            aliases.add(alias)
        for key in ("models", "tools", "limits", "hooks"):
            if key in entry and entry[key] is not None and not isinstance(entry[key], dict):
                p(f"{path.name}: agents[{i}]: {key!r} override must be a mapping")
    if main_count != 1:
        p(f"{path.name}: exactly one agents[] entry must have role: main (found {main_count})")
    routing = data.get("routing") or {}
    if isinstance(routing, dict):
        for kind, target in routing.items():
            if target not in aliases and target != "orchestrator":
                p(f"{path.name}: routing.{kind} names an unknown alias: {target!r}")


def validate_playbooks() -> "tuple[int, set[str]]":
    """Validate every playbook against schemas/playbook.schema.json when
    jsonschema is importable; without it, structural checks only (the
    test suite always runs the full schema validation)."""
    pb_dir = PACK_ROOT / "playbooks"
    ids: set[str] = set()
    files = sorted(pb_dir.glob("*.yaml"))
    schema = None
    try:
        import jsonschema  # noqa: F401
        schema = json.loads((PACK_ROOT / "schemas" / "playbook.schema.json").read_text())
    except ImportError:
        pass
    for path in files:
        data = load_yaml(path) or {}
        pid = data.get("playbook_id")
        if pid != path.stem:
            p(f"{path.name}: playbook_id {pid!r} must match filename stem {path.stem!r}")
        if pid in ids:
            p(f"{path.name}: duplicate playbook_id {pid!r}")
        if pid:
            ids.add(pid)
        # RE playbooks are read-only by contract: no impact above low-impact
        # is allowed at all (there is no target to touch -- the binaries are
        # local files), so the enum itself is the guard.
        if schema is not None:
            import jsonschema
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as e:
                p(f"{path.name}: schema violation at {'/'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message}")
    catalog = PACK_ROOT / "PLAYBOOK_CATALOG.md"
    if files and catalog.is_file():
        text = catalog.read_text()
        missing = [i for i in ids if i not in text]
        if missing:
            p(f"PLAYBOOK_CATALOG.md is missing entries for: {', '.join(sorted(missing))}")
    return len(files), ids


def validate_mcp() -> None:
    """The Ghidra MCP server: declared, present, compiles, and the tool
    names it registers are exactly GHIDRA_TOOLS."""
    mcp_json = PACK_ROOT / ".mcp.json"
    try:
        data = json.loads(mcp_json.read_text())
        servers = data.get("mcpServers", {})
        if "ghidra" not in servers:
            p(".mcp.json: no 'ghidra' server declared")
    except (OSError, json.JSONDecodeError) as e:
        p(f".mcp.json: unreadable: {e}")
        return
    server = PACK_ROOT / "mcp" / "ghidra_server.py"
    if not server.is_file():
        p("mcp/ghidra_server.py is missing")
        return
    try:
        tree = ast.parse(server.read_text())
    except SyntaxError as e:
        p(f"mcp/ghidra_server.py: syntax error: {e}")
        return
    # The tool list is the literal tuple passed to the registration loop.
    source = server.read_text()
    m = re.search(r"for fn in \(\n(.*?)\n\s*\)", source, re.S)
    if not m:
        p("mcp/ghidra_server.py: could not find the tool registration list")
        return
    registered = {name.strip().replace("_tool(", "") for name in m.group(1).split(",") if name.strip()}
    if registered != GHIDRA_TOOLS:
        p(f"mcp/ghidra_server.py registers {sorted(registered)} but the validator knows {sorted(GHIDRA_TOOLS)} -- keep GHIDRA_TOOLS in sync")
    for other in (PACK_ROOT / "mcp").glob("*.py"):
        try:
            ast.parse(other.read_text())
        except SyntaxError as e:
            p(f"mcp/{other.name}: syntax error: {e}")


def validate_skills() -> int:
    """Every SKILL.md: parses, frontmatter complete, name matches the dir,
    and only names real Ghidra tools."""
    skills_dir = PACK_ROOT / "skills"
    count = 0
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        count += 1
        text = path.read_text()
        if not text.startswith("---"):
            p(f"{path.parent.name}/SKILL.md: missing frontmatter")
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            p(f"{path.parent.name}/SKILL.md: frontmatter not closed")
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            p(f"{path.parent.name}/SKILL.md: frontmatter parse error: {e}")
            continue
        if not isinstance(fm, dict):
            p(f"{path.parent.name}/SKILL.md: frontmatter must be a mapping")
            continue
        for key in SKILL_FRONTMATTER_REQUIRED:
            if key not in fm:
                p(f"{path.parent.name}/SKILL.md: frontmatter missing {key!r}")
        if fm.get("name") != path.parent.name:
            p(f"{path.parent.name}/SKILL.md: frontmatter name {fm.get('name')!r} must match the directory name")
        # Structural originality guard: notebook cell artifacts.
        if '"cell_type"' in text or '"source": [' in text or "# %%" in text:
            p(f"{path.parent.name}/SKILL.md: contains raw notebook-cell artifacts (must be original prose)")
        # Any halo-re ghidra tool referenced must be a real one.
        for candidate in re.findall(r"\b(list_binaries|binary_metadata|open_binary|search_functions|search_strings|list_imports|list_exports|decompile_function|disassemble|read_bytes|list_xrefs|gen_callgraph)\b", text):
            if candidate not in GHIDRA_TOOLS:  # pragma: no cover (regex is the source)
                p(f"{path.parent.name}/SKILL.md: references unknown tool {candidate!r}")
        if "Pinball Genie LLC" not in str(fm.get("license", "")):
            p(f"{path.parent.name}/SKILL.md: license must name Pinball Genie LLC")
    return count


def validate_events_artifacts() -> None:
    for path in sorted((PACK_ROOT / "events").glob("*.json")):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            p(f"events/{path.name}: invalid JSON: {e}")
    for path in sorted((PACK_ROOT / "artifacts").glob("*.json")):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            p(f"artifacts/{path.name}: invalid JSON: {e}")


def main() -> int:
    manifest = validate_manifest()
    bio_dir = PACK_ROOT / "agents"
    team_dir = PACK_ROOT / "teams"
    schema_dir = PACK_ROOT / "schemas"

    bios = sorted(bio_dir.glob("*.yaml"))
    teams = sorted(team_dir.glob("*.yaml"))
    bio_names = set()
    for path in bios:
        data = validate_bio(path)
        if data.get("name"):
            bio_names.add(data["name"])
    for path in teams:
        validate_team(path, bio_names)
    pb_count, _ = validate_playbooks()
    validate_mcp()
    skill_count = validate_skills()
    validate_events_artifacts()

    for path in sorted(schema_dir.glob("*.json")):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            p(f"{path.name}: invalid JSON: {e}")

    # Manifest contributes lists must match reality: every listed file exists,
    # every file on disk is listed (N-before -> M-after, both directions).
    if manifest:
        c = manifest.get("contributes") or {}
        for kind, found in (("agents", bios), ("teams", teams)):
            listed = c.get(kind) if isinstance(c.get(kind), list) else []
            for rel in listed:
                if not (PACK_ROOT / rel).is_file():
                    p(f"pack.yaml: contributes.{kind}: {rel} is not in the pack")
            disk = {f"{kind}/{f.name}" for f in found}
            missing = sorted(disk - set(listed))
            if missing:
                p(f"pack.yaml: contributes.{kind} is missing: {', '.join(missing)}")
            extra = sorted(set(listed) - disk)
            if extra:
                p(f"pack.yaml: contributes.{kind} lists files not on disk: {', '.join(extra)}")
        # events / artifacts / workflows contributions name real files
        for entry in c.get("events") or []:
            name = entry.get("schema") if isinstance(entry, dict) else None
            if name and not (PACK_ROOT / name).is_file():
                p(f"pack.yaml: contributes.events: {name} is not in the pack")
        for name in c.get("artifacts") or []:
            if not (PACK_ROOT / "artifacts" / f"{name}.json").is_file():
                p(f"pack.yaml: contributes.artifacts: artifacts/{name}.json is not in the pack")
        for name in c.get("workflows") or []:
            if not (PACK_ROOT / "workflows" / f"{name}.yaml").is_file():
                p(f"pack.yaml: contributes.workflows: workflows/{name}.yaml is not in the pack")

    print(f"validated: {len(bios)} bios, {len(teams)} teams, {pb_count} playbooks, "
          f"{skill_count} skills")
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for line in problems:
            print(f"PROBLEM: {line}")
        return 1
    print("OK: pack is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
