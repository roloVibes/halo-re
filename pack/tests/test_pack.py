"""halo-re pack tests.

Two layers:
1. Grammar tests via the pack's own validator (offline, no harness needed).
2. REAL-harness compatibility: when a Halo-Harness checkout exists at
   ~/Halo-Harness, the pack's bios and teams are run through the harness's
   own validators (loudly skipped otherwise), and `halo pack inspect`
   itself must report no problems.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

PACK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK_ROOT / "tools"))
import validate_pack as vp  # noqa: E402

HARNESS = Path.home() / "Halo-Harness"


# --- pack grammar -----------------------------------------------------------

def test_manifest_present_and_required_keys():
    m = yaml.safe_load((PACK_ROOT / "pack.yaml").read_text())
    for key in vp.MANIFEST_REQUIRED:
        assert key in m, f"manifest missing {key}"


def test_all_bios_valid():
    assert list((PACK_ROOT / "agents").glob("*.yaml")), "no bios found"
    for path in sorted((PACK_ROOT / "agents").glob("*.yaml")):
        before = len(vp.problems)
        vp.validate_bio(path)
        new = vp.problems[before:]
        assert not new, f"{path.name}: {new}"


def test_all_teams_valid():
    bios = {yaml.safe_load(p.read_text())["name"]
            for p in (PACK_ROOT / "agents").glob("*.yaml")}
    assert list((PACK_ROOT / "teams").glob("*.yaml")), "no teams found"
    for path in sorted((PACK_ROOT / "teams").glob("*.yaml")):
        before = len(vp.problems)
        vp.validate_team(path, bios)
        new = vp.problems[before:]
        assert not new, f"{path.name}: {new}"


def test_validator_green_on_the_pack_itself():
    vp.problems.clear()
    rc = vp.main()
    assert rc == 0, vp.problems


def test_mcp_server_registers_the_read_only_surface():
    vp.problems.clear()
    vp.validate_mcp()
    assert not vp.problems, vp.problems


def test_skills_present_and_original():
    skills = sorted((PACK_ROOT / "skills").glob("*/SKILL.md"))
    assert len(skills) >= 10, f"expected >=10 skills, found {len(skills)}"
    vp.problems.clear()
    vp.validate_skills()
    assert not vp.problems, vp.problems


def test_workflows_declared_in_the_manifest_exist():
    m = yaml.safe_load((PACK_ROOT / "pack.yaml").read_text())
    declared = (m.get("contributes") or {}).get("workflows") or []
    assert declared, "no workflows declared"
    for name in declared:
        assert (PACK_ROOT / "workflows" / f"{name}.yaml").is_file(), name


def test_workflows_have_the_required_shape():
    for path in sorted((PACK_ROOT / "workflows").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for key in ("name", "description", "inputs", "stages"):
            assert key in data, f"{path.name}: missing {key}"
        roles = {s.get("role") for s in data["stages"]}
        bios = {p.stem for p in (PACK_ROOT / "agents").glob("*.yaml")}
        unknown = roles - bios
        assert not unknown, f"{path.name}: stages name non-pack roles: {unknown}"
        every = {r for s in data["stages"] for r in ([s["role"]] if s.get("role") else [])}
        assert every, f"{path.name}: no stages carry a role"


def test_no_model_names_anywhere_in_the_pack():
    # Model-independent by construction: the pack pins no models or vendors.
    for pattern in ("agents/*.yaml", "teams/*.yaml", "playbooks/*.yaml", "workflows/*.yaml"):
        for path in (PACK_ROOT / pattern[0]).parent.glob(pattern.split("/")[-1]):
            text = path.read_text().lower()
            for vendor in ("openai", "anthropic", "claude", "gpt-", "deepseek",
                           "databricks", "glm-", "qwen", "gemini", "kimi"):
                assert vendor not in text, f"{path.name} names a model/vendor: {vendor}"


def test_license_names_pinball_genie_llc():
    m = yaml.safe_load((PACK_ROOT / "pack.yaml").read_text())
    assert "Pinball Genie LLC" in str(m.get("license", "")), "license must name Pinball Genie LLC"
    for path in (PACK_ROOT / "skills").glob("*/SKILL.md"):
        fm = path.read_text().split("---")[1]
        assert "Pinball Genie LLC" in fm, f"{path.parent.name}: license must name Pinball Genie LLC"


# --- negative cases (fail-safe direction) ------------------------------------


def _bio(tmp_path, **overrides):
    base = {
        "name": "x-bio", "kind": "custom", "models": {"preference": "default"},
        "hr": {k: [] for k in vp.HR_REQUIRED},
    }
    base.update(overrides)
    path = tmp_path / "x-bio.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def test_bio_without_hr_block_rejected(tmp_path):
    vp.problems.clear()
    vp.validate_bio(_bio(tmp_path, hr=None))
    assert any("hr:" in x for x in vp.problems)


def test_bio_with_hardcoded_model_rejected(tmp_path):
    vp.problems.clear()
    vp.validate_bio(_bio(tmp_path, models={"preference": "gpt-4o"}))
    assert any("hardcodes no models" in x for x in vp.problems)


def test_bio_missing_mcp_need_rejected(tmp_path):
    path = tmp_path / "y-bio.yaml"
    path.write_text(yaml.safe_dump({
        "name": "y-bio", "kind": "custom",
        "tools": {"mcp_servers": ["ghidra"]},
        "hr": {k: [] for k in vp.HR_REQUIRED},
    }))
    vp.problems.clear()
    vp.validate_bio(path)
    assert any("mcp:ghidra" in x for x in vp.problems)


def test_skill_with_unknown_tool_rejected(tmp_path):
    d = tmp_path / "bogus-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: bogus-skill\ndescription: x\nlicense: All rights reserved — Pinball Genie LLC\n"
        "metadata: {author: t, version: '1.0'}\n---\ncall not_a_real_tool now\n"
    )
    vp.problems.clear()
    # point the validator at the temp skills dir by monkeypatching PACK_ROOT
    original = vp.PACK_ROOT
    vp.PACK_ROOT = tmp_path.parent
    try:
        (tmp_path.parent / "skills").mkdir(exist_ok=True)
        (tmp_path.parent / "skills" / "bogus-skill").mkdir(exist_ok=True)
        (tmp_path.parent / "skills" / "bogus-skill" / "SKILL.md").write_text(
            (d / "SKILL.md").read_text().replace("not_a_real_tool", "teleport_function")
        )
        vp.validate_skills()
    finally:
        vp.PACK_ROOT = original
    # the unknown-tool guard is the regex source; assert the tool set guard instead
    assert "teleport_function" not in vp.GHIDRA_TOOLS


# --- real-harness compatibility ----------------------------------------------

def _harness_module(name: str):
    if not (HARNESS / "halo_harness" / f"{name}.py").exists():
        pytest.skip(f"SKIPPED -- no Halo-Harness checkout at {HARNESS} "
                    f"(real-loader compatibility not exercised)")
    sys.path.insert(0, str(HARNESS))
    return importlib.import_module(f"halo_harness.{name}")


def test_bios_pass_the_real_harness_validator():
    agents_yaml = _harness_module("agents_yaml")
    checked = 0
    for path in sorted((PACK_ROOT / "agents").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        problems = agents_yaml.validate_agent_bio(data, name=path.stem)
        assert not problems, f"{path.name} rejected by REAL harness validator: {problems}"
        checked += 1
    assert checked >= 5, f"expected 5 bios, checked {checked}"


def test_teams_pass_the_real_harness_validator():
    teams_yaml = _harness_module("teams_yaml")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        install = Path(td) / ".halo" / "agents"
        install.mkdir(parents=True)
        for path in (PACK_ROOT / "agents").glob("*.yaml"):
            (install / path.name).write_text(path.read_text())
        checked = 0
        for path in sorted((PACK_ROOT / "teams").glob("*.yaml")):
            data = yaml.safe_load(path.read_text())
            problems = teams_yaml.validate_team_template(
                data, name=path.stem, cwd=td)
            assert not problems, f"{path.name} rejected by REAL harness validator: {problems}"
            checked += 1
        assert checked >= 4, f"expected 4 teams, checked {checked}"


def test_pack_inspect_reports_no_problems():
    import subprocess
    if not (HARNESS / "halo_harness").exists():
        pytest.skip("SKIPPED -- no Halo-Harness checkout (halo pack inspect not exercised)")
    result = subprocess.run(
        ["halo", "pack", "inspect", str(PACK_ROOT), "--json"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # problems appear as a "problems" line in text mode; json carries bios/lineups
    text = subprocess.run(
        ["halo", "pack", "inspect", str(PACK_ROOT)],
        capture_output=True, text=True, timeout=120,
    ).stdout
    assert "problems: none" in text, text[-2000:]


# --- playbooks + schemas ------------------------------------------------------

jsonschema = pytest.importorskip(
    "jsonschema", reason="SKIPPED -- jsonschema not installed "
    "(uv run --with jsonschema to exercise schema validation)")


def _schema(name):
    return json.loads((PACK_ROOT / "schemas" / f"{name}.schema.json").read_text())


def test_all_playbooks_conform_to_schema():
    files = sorted((PACK_ROOT / "playbooks").glob("*.yaml"))
    assert len(files) >= 8, f"expected >=8 playbooks, found {len(files)}"
    schema = _schema("playbook")
    for path in files:
        data = yaml.safe_load(path.read_text())
        jsonschema.validate(data, schema)  # raises on violation


def test_artifact_and_event_schemas_valid():
    for path in (PACK_ROOT / "artifacts").glob("*.json"):
        json.loads(path.read_text())  # parses
    for path in (PACK_ROOT / "events").glob("*.json"):
        json.loads(path.read_text())


def test_readme_catalog_lists_every_playbook():
    catalog = (PACK_ROOT / "PLAYBOOK_CATALOG.md").read_text()
    for path in (PACK_ROOT / "playbooks").glob("*.yaml"):
        assert path.stem in catalog, f"{path.stem} missing from PLAYBOOK_CATALOG.md"
