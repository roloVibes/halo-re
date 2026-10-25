---
name: binary-triage
description: >-
  CLI-first triage ladder (file, nm -U, strings, otool -L / objdump -p)
  run BEFORE any Ghidra import, then a WHERE/WHAT dual classification
  into a JSON verdict with evidence. Use it on every unfamiliar binary
  so an unknown sample costs seconds of shell time instead of a 40-minute
  Ghidra import.
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Binary Triage — classify before you import

First contact with an unknown binary is answered from the shell, not
from Ghidra. A handful of CLI tools establish where the binary runs and
what it probably is in seconds; importing the same binary into Ghidra
can take ~40 minutes for a 20,000-function dylib and a large slab of
RAM. This skill walks the cheap ladder first, classifies the sample on
two independent axes (WHERE it runs, WHAT it is), and emits a JSON
verdict that decides whether a Ghidra session is warranted at all.

## Use this skill when
- an unknown or untrusted binary lands in scope and nothing is known
  about it yet
- deciding whether to spend a Ghidra import on a target (the verdict
  field is that decision, with evidence)
- a batch of samples must be prioritized and only some deserve depth
- a previously triaged binary came back with a different hash — re-run,
  don't reuse the old verdict

## Workflow Overview

1. **`file <binary>`** — format, arch, and linkage in one line. This is
   the WHERE axis seed: Mach-O vs ELF vs PE, 64-bit vs 32-bit, arm64 vs
   x86_64, statically or dynamically linked, stripped or not.
2. **`nm -U <binary>`** — defined (non-external) symbols. Named
   functions are a free function inventory; a near-empty output on an
   unstripped binary is itself a finding (packed/obfuscated). On macOS
   this reads Mach-O natively.
3. **`strings -a <binary>`** (page through; `| grep -iE` for the
   categories below) — collect:
   - URLs and domains (C2, update checks, telemetry)
   - IP addresses (hardcoded peers)
   - filesystem paths (droppers, persistence locations)
   - registry keys (`HKLM\...`, `SOFTWARE\Microsoft\Windows\...`)
   - credential-looking material (`password`, `token`, base64-looking
     blobs, key material near crypto constants)
   - cover-story narratives — polished error dialogs, fake EULA or
     installer text that exists to make malware look benign; note it as
     such rather than as evidence of legitimacy.
4. **`otool -L <binary>` (macOS) / `objdump -p <binary>` (ELF)** —
   linked libraries and, on ELF, the full dynamic section (RPATH,
   needed sonames, flags). This is the import surface the WHAT axis
   leans on hardest.
5. **Classify WHERE from headers** (steps 1, 4): platform, architecture,
   endianness. These are mechanical facts read off the header — report
   them as facts, not guesses.
6. **Classify WHAT from strings + imports**, as `binary_type` plus a
   `confidence` plus the literal `evidence` that supports it (import
   names, string values, symbol names). Tag security-relevant import
   clusters when present:
   - **memory**: `memcpy`/`memmove` with suspicious sizes, `VirtualAlloc`,
     `mmap`+`mprotect` pairs (unpacking, shellcode)
   - **process**: `CreateProcess*`, `fork`/`exec*`, `posix_spawn`,
     `OpenProcess`+`WriteProcessMemory` (injection)
   - **network**: `socket`/`connect`, `WSAStartup`, `InternetOpen*`,
     `HttpSendRequest`, raw URLs from step 3
   - **crypto**: `CryptAcquireContext*`, `EVP_*`, `BCrypt*`, or
     recognizable constant tables (RC5/RC6 S-box values, MD5/SHA init
     vectors) that indicate hand-rolled crypto.
7. **Refuse naive classifiers.** Never assign binary_type from the file
   extension or a keyword hunt: samples arrive with no extension, with
   version-suffixed names (`libFoo.5.dylib`, `libc.so.6`), or renamed to
   impersonate system files. The classification must cite header +
   import + string evidence, and confidence drops when the only support
   is a filename.
8. **Emit the verdict.** Map the accumulated evidence to exactly one:
   `deep-dive recommended` (security-relevant import clusters, C2
   indicators, or obfuscation signs — a full Ghidra session via the
   ghidra-mcp-usage skill is warranted), `targeted review` (a specific
   question is answerable from a few functions — import, but only query
   around the target), or `low priority` (benign-looking, well-known
   provenance — park it). Every verdict carries its evidence.

## Output Schema
```json
{
  "skill": "binary-triage",
  "binary": "/abs/path/to/sample",
  "where": {"platform": "darwin", "arch": "arm64", "endianness": "little", "format": "Mach-O 64-bit", "source": "file + otool"},
  "what": {
    "binary_type": "info-stealer | loader | dropper | driver | library | utility | unknown",
    "confidence": "high | medium | low",
    "evidence": ["import: CFNetwork (network)", "string: 'https://example.org/gate.php'", "symbol: getEncryptionKey"]
  },
  "import_categories_present": ["network", "crypto"],
  "strings_of_interest": {"urls": [], "ips": [], "paths": [], "registry_keys": [], "credential_material": [], "cover_story": []},
  "verdict": "deep-dive recommended | targeted review | low priority",
  "verdict_rationale": "network + crypto clusters plus a hardcoded URL; symbols unstripped",
  "ghidra_warranted": true
}
```

## When NOT to Use This Skill
- The binary's provenance and type are already established — go straight
  to ghidra-mcp-usage (or token-budget-a-binary for a prompt-budget call).
- You need decompiled code, call graphs, or xrefs — the CLI ladder
  cannot produce those; this skill only decides *whether* to pay for them.
- Live/dynamic analysis: everything here is static. A packed sample may
  triage as an uninformative loader; that is an honest `low`-confidence
  WHAT, not a wrong one — note it and consider detonation elsewhere.
- Comparing two builds of the same binary — that is diff work, not
  first-contact triage.
