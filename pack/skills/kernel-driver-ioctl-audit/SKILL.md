---
name: kernel-driver-ioctl-audit
description: >-
  Audit a Windows kernel driver's IOCTL attack surface end to end: locate DriverEntry
  (with CRT-stub fallbacks), decode the IRP dispatch table, extract and CTL_CODE-decode
  every IOCTL, and scan each handler against a CWE-tagged vulnerability pattern table.
  Produces a JSON report of IOCTLs, findings, and mitigating evidence. Use when handed a
  .sys file or asked "what IOCTLs does this driver expose and are any handlers unsafe".
license: All rights reserved — Pinball Genie LLC
metadata:
  author: rolo (roloVibes)
  version: "1.0"
---
# Windows Kernel Driver IOCTL Audit

Map a Windows kernel driver's user-reachable attack surface: which IRP major functions
it registers, every IOCTL code its device-control handler accepts, and which of those
paths mishandle user-supplied buffers. The workflow runs top-down — entry point to
dispatch table to handler to per-IOCTL validation — so every finding is anchored to a
decompiled function, not to an import name or a guess. All Ghidra work goes through the
pack's read-only MCP tools (mcp server "ghidra" in a Halo session): `list_binaries`,
`binary_metadata`, `open_binary`, `search_functions`, `search_strings`, `list_imports`,
`list_exports`, `decompile_function`, `disassemble`, `read_bytes`, `list_xrefs`,
`gen_callgraph`.

## Use this skill when
- The target is a Windows kernel driver (.sys, x64 PE) and the question is its IOCTL attack surface.
- You need a dispatch-table map (which handler serves IRP_MJ_DEVICE_CONTROL and friends).
- You must judge whether specific IOCTL handlers validate user buffers correctly.
- A pentest/audit needs an evidence-backed, per-IOCTL finding list with CWE references.

## Workflow Overview
1. **Confirm the target is loaded.** Call `list_binaries` first — always. If the driver
   is not in the project, ask before calling `open_binary` (full Ghidra auto-analysis is
   expensive on first open). Note: project binary names carry a `-<hash>` suffix, so
   match the user's filename as a prefix, never exactly.
2. **Verify it is an x64 Windows driver.** Call `binary_metadata` on the target and
   check the language/processor and executable format. The struct offsets below are
   x64-specific; on 32-bit the numbers change and this skill does not apply as written.
3. **Find the real entry point.** Call `search_functions` with `DriverEntry`. If nothing
   comes back, retry with `GsDriverEntry`, then just `entry` — drivers built against the
   CRT get a stub (`GsDriverEntry` or `entry`) that tail-calls the real DriverEntry, so
   decompile the stub and follow its call. Decompile the result with `decompile_function`
   (a unique substring of the name is enough; raise `max_lines` only if you need the tail).
4. **Decode the IRP dispatch table.** In the DriverEntry decompilation, look for writes
   into the DRIVER_OBJECT's MajorFunction array, which starts at **+0x70 on x64** with one
   8-byte slot per IRP major code. Two forms appear:
   - Direct: `*(code **)(param_1 + 0xe0) = Handler` — the slot index is
     `(0xe0 - 0x70) / 8 = 0x0e` = **IRP_MJ_DEVICE_CONTROL**.
   - Loop: a loop storing handlers into consecutive slots — slot `n` corresponds to
     IRP major code `n` counting from IRP_MJ_CREATE (0x00).
   If DriverEntry contains no such writes, the registration lives in a helper —
   `list_xrefs` on DriverEntry is not enough here; decompile its callees (typically named
   `Initialize` or `SetIrpFunctions` in drivers with symbols) and look there.
5. **Reach the actual device-control handler.** Decompile the function stored into the
   IRP_MJ_DEVICE_CONTROL slot. **Thunk heuristic:** a handler that decompiles to fewer
   than 5 lines is a thunk — it just forwards; decompile its single callee and audit that
   instead. If the dispatch table was unreadable, fall back to `search_functions` with
   `DeviceControl` or `Ioctl` and confirm via `list_xrefs` that DriverEntry's registration
   chain reaches it.
6. **Extract the IOCTL codes.** In the handler, the control code is read from the current
   IO_STACK_LOCATION at **+0x18 on x64** (OutputBufferLength at +0x8, InputBufferLength
   at +0x10, Type3InputBuffer at +0x20; `Irp->UserBuffer` sits at +0x70 inside _IRP).
   Walk every `== 0x…` comparison and `case 0x…:` label, pair each code with the function
   called on that branch, and **reject values in the NTSTATUS range (0xC0000000 and up)**
   — those are status codes, not IOCTLs. Decode each surviving code with the CTL_CODE
   layout: `device = code >> 16`, `access = (code >> 14) & 3`, `function = (code >> 2) & 0xFFF`,
   `method = code & 3`. Sanity-check the decoded device type; implausible device types
   mean you grabbed the wrong comparison.
7. **Scan each IOCTL branch against the pattern table (below), immediately after the
   IOCTL map exists.** Decompile the handler (or per-code helper) for every extracted
   code with `decompile_function` and check each pattern. Record mitigating evidence —
   a `ProbeForRead`/`ProbeForWrite` or a length comparison you observed — as an
   informational note, NOT as a finding. A handler may be reported clean only when it
   shows BOTH a probe AND a length comparison on the path in question.
8. **Emit the report.** Produce the JSON in the Output Schema below as the final step.
   Every finding must quote the decompiled lines that triggered it.

**Pattern table:**

| ID | Pattern | CWE |
|----|---------|-----|
| V0 | METHOD_NEITHER IOCTL whose handler lacks ProbeForRead/ProbeForWrite | CWE-822 |
| V1 | Type3InputBuffer or Irp->UserBuffer dereferenced with no preceding probe | CWE-822 |
| V2 | Handler never compares InputBufferLength/OutputBufferLength against what it reads/writes | CWE-1284 |
| V3 | memcpy / RtlCopyMemory / strcpy on a path with no length comparison | CWE-787 |
| V4 | Dangerous kernel APIs reachable from a handler: MmMapIoSpace, MmMapLockedPagesSpecifyCache, ZwMapViewOfSection | CWE-782 |
| V5 | Process/handle manipulation reachable from a handler: PsLookupProcessByProcessId, KeStackAttachProcess, ObReferenceObjectByHandle | CWE-269 / CWE-1288 |

## Output Schema
```json
{
  "binary": "string (project name incl. -hash suffix)",
  "arch": "x64",
  "entry_point": "string (function actually audited)",
  "dispatch": {
    "irp_mj_device_control_handler": "string",
    "thunk_followed": true
  },
  "ioctls": [
    {
      "code": "0x...",
      "device": "0x...",
      "access": 0,
      "function": "0x...",
      "method": "METHOD_NEITHER|METHOD_BUFFERED|METHOD_IN_DIRECT|METHOD_OUT_DIRECT",
      "handler": "string",
      "status": "clean|finding|info",
      "findings": [{"pattern": "V0", "cwe": "CWE-822", "evidence": "quoted decompiled lines"}],
      "mitigations": ["probe observed at ...", "length check observed at ..."]
    }
  ],
  "summary": "string: counts of findings by pattern, overall assessment"
}
```

## When NOT to Use This Skill
- The target is not a Windows kernel driver — user-mode PE, .so, or Mach-O binaries need
  different struct layouts and offsets; use kernel-api-audit or macho-triage-diff instead.
- The binary is a 32-bit driver — every offset in this skill (+0x70, +0xe0, +0x18, +0x70
  in _IRP, 8-byte slots) is x64-only and silently wrong on x86.
- You only need "what can this driver do" (capability question) — that is the
  kernel-api-audit skill; this one is specifically the IOCTL surface.
- You were asked to diff two versions of a driver — use patch-diff-analysis first and
  come back to this for the changed handlers.
