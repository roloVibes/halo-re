# PLAYBOOK_CATALOG.md

## Shipped (0.1.0) — all 8 validated against schemas/playbook.schema.json

Every playbook is model-independent (enforced by test); every stage is
read-only or low-impact (importing a binary into the LOCAL Ghidra project is
the only side effect the schema allows); findings require quoted decompiled
evidence (enforced by the vuln-reviewer gate).

| ID | Phase | Category | Methodology ref |
|---|---|---|---|
| triage.binary-inventory | triage | triage | halo-re:binary-triage |
| triage.platform-classify | triage | triage | halo-re:binary-triage |
| audit.kernel-ioctl | audit | audit | halo-re:kernel-driver-ioctl-audit, CWE-822/1284/787/782 |
| audit.kernel-api | audit | audit | halo-re:kernel-api-audit |
| audit.import-surface | audit | audit | halo-re:binary-triage (exact-name risk model) |
| diff.patch-cve | diff | diff | halo-re:patch-diff-analysis |
| static.semgrep-decompiled | static | static | halo-re:semgrep-decompiled, CWE-416/190/787 |
| report.draft-from-confirmed | reporting | reporting | artifacts/re-finding-report.json |

Workflows (halo workflow run halo-re/&lt;name&gt;): `triage`, `semgrep-triage`.
