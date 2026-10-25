#!/usr/bin/env python3
"""halo-re pack -- the read-only Ghidra MCP server.

FastMCP (stdio) over the pyghidra core in ghidra_core.py. Declared in
.mcp.json, granted with `halo pack enable halo-re --grant mcp:ghidra`.

Tool surface (all read-only except open_binary, which exists because
importing the target you were pointed at IS the workflow -- it runs full
Ghidra analysis on first open, so the skills say to confirm the target):

  list_binaries            what is in the project (call this FIRST)
  binary_metadata          platform / arch / format / function count
  open_binary              import + analyze a binary (expensive, once)
  search_functions         substring search over the function manager
  search_strings           defined strings (optionally filtered)
  list_imports             external symbols, paged (offset/limit)
  list_exports             exported entry points
  decompile_function       Ghidra decompiled C for a name or address
  disassemble              instruction listing for a function
  read_bytes               raw bytes at an address
  list_xrefs               callers and callees of a function
  gen_callgraph            edge list around a function, trimmed

Design contract (measured on the agentic-RE course stack):
- every tool returns a compact JSON-able dict; strings, never exceptions;
  every error says what to do next (the agent loop degrades gracefully
  only if failures are legible);
- result lists are capped and paged; decompilation truncated (an LLM
  budget is a real budget);
- binary names carry a -<hash> suffix in Ghidra projects, so prefix
  matching is the rule everywhere;
- multi-binary: pass `binary=` to any tool or omit it when only one is
  open (list_binaries first, always).
"""

from __future__ import annotations

import functools
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # ghidra_core beside this file

from ghidra_core import (  # noqa: E402
    AnalysisSession,
    DEFAULT_PROJECT_DIR,
    GhidraProblem,
    detect_install,
    resolve_project_dir,
)

MAX_RESULT_CHARS = 60_000
PAGE_DEFAULT = 100


def _clip(obj) -> dict:
    """One shape for truncation, applied uniformly."""
    text = json.dumps(obj, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return obj
    return {
        "status": "truncated",
        "note": f"result exceeded {MAX_RESULT_CHARS} chars; narrow the query (offset/limit, a longer function-name prefix, or a filter)",
        "keys": list(obj.keys()) if isinstance(obj, dict) else [],
    }


def _config_path(key: str, default: str = "") -> str:
    """Read a pack setting through Halo's extension API when available.

    The server normally runs under Halo (PYTHONPATH carries halo_harness);
    standalone (tests, manual runs) fall back to the default.
    """
    try:
        from halo_harness.ext import get_config  # type: ignore

        value = get_config("halo-re", key, default)
        return str(value) if value else default
    except Exception:
        return default


def _publish(kind: str, data: dict) -> None:
    """A Studio live-feed frame, best effort: never fail a tool for an event."""
    try:
        from halo_harness.ext import publish_event  # type: ignore

        publish_event("halo-re", kind, data)
    except Exception:
        pass


SESSION: AnalysisSession | None = None


@asynccontextmanager
async def _lifespan(server):
    """Open the Ghidra project ONCE; every tool call reads from it."""
    global SESSION
    try:
        install_dir = detect_install(
            explicit=_config_path("ghidra_install_dir"),
        )
        project_dir = resolve_project_dir(_config_path("project_dir") or DEFAULT_PROJECT_DIR)
        SESSION = AnalysisSession(install_dir, project_dir)
        # Binaries named at startup skip the open_binary round-trip.
        for raw in os.environ.get("HALO_RE_BINARIES", "").split(os.pathsep):
            if raw.strip():
                try:
                    SESSION.open(raw.strip())
                except GhidraProblem:
                    pass  # list_binaries reports what actually loaded
        _publish("re.session", {"state": "opened", "install_dir": install_dir, "project_dir": project_dir})
    except GhidraProblem as problem:
        # A broken environment must not crash the server process: the tools
        # answer with the remedy, so the agent can surface it.
        SESSION = None  # type: ignore[assignment]
        _publish("re.session", {"state": "failed", "problem": str(problem)})
    try:
        yield {}
    finally:
        if SESSION is not None:
            SESSION.close()


def _needs_session() -> AnalysisSession:
    if SESSION is None:
        raise GhidraProblem(
            "the Ghidra session is not running (no usable install or the deps are missing). "
            "Run the halo-re:ghidra-doctor skill; it verifies the install by effect and "
            "names the exact fix."
        )
    return SESSION


def _tool(fn):
    """Wrap a tool function: GhidraProblem -> an error dict, never a crash.

    functools.wraps keeps the typed signature visible: FastMCP builds each
    tool's parameter schema from inspect.signature, which follows
    __wrapped__ -- a bare *args/**kwargs wrapper would publish a schema
    demanding literal 'args' and 'kwargs' (measured in the smoke test).
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return _clip(fn(*args, **kwargs))
        except GhidraProblem as problem:
            return {"error": str(problem)}
    return wrapped


# ---------------------------------------------------------------------------
# the tools
# ---------------------------------------------------------------------------

def list_binaries() -> dict:
    """List every binary in the open Ghidra project. Call this FIRST in any
    analysis session so you know what you can query before importing anything."""
    session = _needs_session()
    programs = [
        {"name": name, "language": str(prog.getLanguageID())}
        for name, prog in sorted(session.programs.items())
    ]
    return {"status": "ok", "binaries": programs, "count": len(programs)}


def binary_metadata(binary: str = "") -> dict:
    """Platform, architecture, format and function count for one binary."""
    session = _needs_session()
    name, program = session.require(binary or None)
    lang = program.getLanguage()
    fm = program.getFunctionManager()
    return {
        "status": "ok",
        "binary": name,
        "language_id": str(program.getLanguageID()),
        "processor": str(lang.getProcessor()),
        # SleighLanguage has no getEndian (measured); the description carries it
        "endian": str(lang.getLanguageDescription().getEndian()),
        "function_count": fm.getFunctionCount(),
        "executable_format": str(program.getExecutableFormat()),
        "image_base": str(program.getImageBase()),
    }


def open_binary(path: str) -> dict:
    """Import a binary into the project and analyze it. EXPENSIVE on first
    open (full Ghidra auto-analysis: ~1 min for a small binary, much longer
    for drivers or big dylibs); subsequent opens are instant. Confirm the
    target with the user before calling unless they named it."""
    session = _needs_session()
    return session.open(path)


def search_functions(query: str, binary: str = "", limit: int = 10) -> dict:
    """Case-insensitive substring search over all functions. Returns at most
    `limit` (default 10) matches as 'name @ entry_point' lines. If nothing
    matches, try a shorter/broader query."""
    session = _needs_session()
    _, program = session.require(binary or None)
    fm = program.getFunctionManager()
    low = query.lower()
    hits = []
    for func in fm.getFunctions(True):
        name = str(func.getName())
        if low in name.lower():
            hits.append({"name": name, "entry_point": str(func.getEntryPoint())})
            if len(hits) >= limit:
                break
    if not hits:
        return {"status": "ok", "results": [], "hint": "no match; try a shorter substring (e.g. 'ioctl', 'entry', 'validate')"}
    return {"status": "ok", "results": hits, "count": len(hits), "truncated_at": limit}


def search_strings(filter_text: str = "", binary: str = "", limit: int = 50) -> dict:
    """Defined strings in the binary, newest-first scan order, optionally
    filtered by substring. Useful for C2 URLs, paths, registry keys, format
    strings, and cover-story narratives (see the re-agent-security skill)."""
    session = _needs_session()
    _, program = session.require(binary or None)
    listing = program.getListing()
    low = (filter_text or "").lower()
    hits = []
    for data in listing.getDefinedData(True):
        try:
            if not data.hasStringValue():
                continue
            value = str(data.getValue())
        except Exception:
            continue
        if low and low not in value.lower():
            continue
        hits.append({"address": str(data.getAddress()), "value": value})
        if len(hits) >= limit:
            break
    return {"status": "ok", "results": hits, "count": len(hits), "truncated_at": limit}


def list_imports(binary: str = "", offset: int = 0, limit: int = PAGE_DEFAULT) -> dict:
    """External symbols (imported functions). PAGES: keep calling with a
    higher offset until a short page comes back."""
    session = _needs_session()
    _, program = session.require(binary or None)
    table = program.getSymbolTable()
    all_imports = [
        {"name": str(sym.getName()), "address": str(sym.getAddress())}
        for sym in table.getExternalSymbols()
    ]
    page = all_imports[offset : offset + limit]
    return {
        "status": "ok",
        "total_imports": len(all_imports),
        "offset": offset,
        "limit": limit,
        "results": page,
        "more": offset + limit < len(all_imports),
    }


def list_exports(binary: str = "") -> dict:
    """Exported entry points of the binary."""
    session = _needs_session()
    name, program = session.require(binary or None)
    table = program.getSymbolTable()
    out = []
    it = table.getExternalEntryPointIterator()
    while it.hasNext():
        addr = it.next()
        for sym in table.getSymbolsAt(addr):
            out.append({"name": str(sym.getName()), "address": str(addr)})
    return {"status": "ok", "binary": name, "exports": out, "count": len(out)}


def decompile_function(name_or_address: str, binary: str = "", max_lines: int = 400) -> dict:
    """Decompiled C for one function, by exact name, by address (0x...), or
    by unique substring. The default truncates at 400 lines; raise max_lines
    only when you need the tail. The entry-point search falls back to
    GsDriverEntry/entry when DriverEntry is absent (CRT stubs tail-call it)."""
    session = _needs_session()
    return session.decompile(binary or None, name_or_address, max_lines=max_lines)


def disassemble(name_or_address: str, binary: str = "", max_instructions: int = 100) -> dict:
    """Instruction listing for a function (address, mnemonic, bytes)."""
    session = _needs_session()
    _, program = session.require(binary or None)
    func = session._find_function(program, name_or_address)
    if func is None:
        return {"error": f"no function matches {name_or_address!r}; search_functions first"}
    listing = program.getListing()
    out = []
    for insn in listing.getInstructions(func.getBody(), True):
        out.append({"address": str(insn.getAddress()), "text": str(insn)})
        if len(out) >= max_instructions:
            break
    return {"status": "ok", "function": str(func.getName()), "instructions": out, "count": len(out)}


def read_bytes(address: str, length: int = 64, binary: str = "") -> dict:
    """Raw bytes at an address, hex-encoded, capped at 4096."""
    session = _needs_session()
    _, program = session.require(binary or None)
    addr = session._to_addr(program, address)
    if addr is None:
        return {"error": f"{address!r} is not an address in this binary"}
    length = max(1, min(length, 4096))
    try:
        data = bytes(program.getMemory().getBytes(addr, length))
    except Exception as exc:
        return {"error": f"read failed at {address}: {exc}"}
    return {"status": "ok", "address": str(addr), "length": len(data), "hex": data.hex()}


def list_xrefs(name: str, binary: str = "") -> dict:
    """Callers (references to) and callees (references from) for a function.
    For an IMPORT, xref its __imp_<Name> label rather than the bare external
    symbol -- that is where calling functions point."""
    session = _needs_session()
    _, program = session.require(binary or None)
    func = session._find_function(program, name)
    if func is None:
        return {"error": f"no function matches {name!r}; search_functions first"}
    monitor = None
    callers = sorted({str(f.getName()) for f in func.getCallingFunctions(monitor)})
    callees = sorted({str(f.getName()) for f in func.getCalledFunctions(monitor)})
    return {
        "status": "ok",
        "function": str(func.getName()),
        "callers": callers,
        "callees": callees,
    }


def gen_callgraph(seed: str, direction: str = "callers", max_edges: int = 60, binary: str = "") -> dict:
    """Edges around a seed function (callers or callees), trimmed to
    max_edges, plus how much was trimmed -- for readable call-graph views."""
    if direction not in ("callers", "callees"):
        return {"error": "direction must be 'callers' or 'callees'"}
    session = _needs_session()
    _, program = session.require(binary or None)
    func = session._find_function(program, seed)
    if func is None:
        return {"error": f"no function matches {seed!r}; search_functions first"}
    monitor = None
    edges: list[dict] = []
    trimmed = 0
    frontier = [func]
    seen: set = set()
    while frontier and len(edges) < max_edges:
        current = frontier.pop(0)
        key = str(current.getEntryPoint())
        if key in seen:
            continue
        seen.add(key)
        related = (
            current.getCallingFunctions(monitor) if direction == "callers" else current.getCalledFunctions(monitor)
        )
        for other in related:
            edge = (
                {"from": str(other.getName()), "to": str(current.getName())}
                if direction == "callers"
                else {"from": str(current.getName()), "to": str(other.getName())}
            )
            if len(edges) < max_edges:
                edges.append(edge)
                if str(other.getEntryPoint()) not in seen:
                    frontier.append(other)
            else:
                trimmed += 1
    return {
        "status": "ok",
        "seed": str(func.getName()),
        "direction": direction,
        "edges": edges,
        "shown_edges": len(edges),
        "trimmed": trimmed,
    }


# ---------------------------------------------------------------------------

def build_server():
    from mcp.server.fastmcp import FastMCP
    from mcp.server import Server

    mcp = FastMCP("halo-re-ghidra", lifespan=_lifespan)

    for fn in (
        list_binaries,
        binary_metadata,
        open_binary,
        search_functions,
        search_strings,
        list_imports,
        list_exports,
        decompile_function,
        disassemble,
        read_bytes,
        list_xrefs,
        gen_callgraph,
    ):
        wrapped = _tool(fn)
        mcp.tool()(wrapped)

    # silence the unused-import lint for Server (referenced in the type hint)
    _ = Server
    return mcp


def main() -> int:
    server = build_server()
    server.run()  # stdio
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
