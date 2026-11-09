"""Halo RE's own test. Run it from the pack's folder:

    python -m tests.pack_test

It runs `halo_harness.ext.testing` -- the same checks `halo pack test .` makes, in a scratch home and project, never a
model call, never the network -- and then the pack's own checks in `own_checks` below. Add yours there: each is one
`report.add(file, what, ok, fix)`, and a failed one prints `<file>: <what> -- <fix>` like every other.
"""

import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent

try:
    from halo_harness.ext import testing
except ImportError:  # the harness is not importable on this interpreter
    testing = None

#: The `hr:` block every bio in this pack must carry (the RE-role contract; tools/validate_pack.py).
HR_REQUIRED = ("responsibility", "boundaries", "inputs", "outputs", "evidence_requirements", "completion_criteria")


def _listed(kind: str) -> set:
    contributes = (testing.manifest(PACK).get("contributes") or {})
    return {Path(str(rel)).name for rel in contributes.get(kind) or []}


def own_checks(report) -> None:
    """The pack's own checks, after the standard ones."""
    import yaml

    report.add("pack.yaml", "the pack's id is halo-re", testing.manifest(PACK).get("id") == "halo-re",
               "the id in pack.yaml is the pack's name everywhere: keep it as the folder's name")

    for kind in ("agents", "teams"):
        listed, disk = _listed(kind), {p.name for p in (PACK / kind).glob("*.yaml")}
        report.add("pack.yaml", f"every {kind}/*.yaml is listed in contributes.{kind}", listed == disk,
                   f"contributes.{kind} and {kind}/ disagree: only listed {sorted(listed - disk)}, "
                   f"only on disk {sorted(disk - listed)}")

    missing = []
    for path in sorted((PACK / "agents").glob("*.yaml")):
        hr = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("hr") or {}
        missing += [f"{path.name}: hr.{key}" for key in HR_REQUIRED if key not in hr]
    report.add("agents/", "every bio declares the full hr: RE-role contract", not missing,
               "; ".join(missing) or "each bio carries hr.responsibility, hr.boundaries, hr.inputs, hr.outputs, "
                                     "hr.evidence_requirements and hr.completion_criteria")

    models = [p.name for p in (PACK / "agents").glob("*.yaml")
              if ((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("models") or {}).get("preference")
              not in (None, "default")]
    report.add("agents/", "no bio pins a model", not models,
               f"these bios name a model: {models} -- a pack stays model-agnostic (models.preference: default)")


def main() -> int:
    if testing is None:
        # Visible, never silent: `halo pack test .` is the same check with the
        # harness in place, and it is what CI runs.
        print("SKIPPED -- halo_harness is not importable on this interpreter "
              "(pip install git+https://github.com/roloVibes/Halo-Harness, or run `halo pack test .`)")
        return 0
    report = testing.run(PACK)
    own_checks(report)
    print(report.text())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
