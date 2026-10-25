"""halo-re pack -- the Ghidra core the MCP server drives.

Everything Ghidra-specific lives here so the server file is only tool
plumbing. Design rules (each one measured the hard way, see
docs/GHIDRA-NOTES.md):

- Detect a Ghidra install BY EFFECT, never by `which ghidra`: the release
  ships `ghidraRun` and `support/analyzeHeadless`, no `ghidra` binary, and a
  zip-extract install puts neither on PATH.
- Ghidra refuses any path element beginning with a dot
  (`IllegalArgumentException: Path element starting with '.' is not
  permitted`), so projects NEVER live under ~/.local/share or ~/.halo;
  the default is ~/ghidra-projects.
- GHIDRA_INSTALL_DIR must be in os.environ BEFORE pyghidra.start(); a
  subprocess that inherits a clean env silently fails otherwise.
- pyghidra.open_program / GhidraProject.open_program IMPORTS AND ANALYZES on
  first open (30-60 s for a small binary, minutes for drivers, ~40 min for a
  20k-function dylib). The server opens binaries ONCE and serves every tool
  call from the open project; the doctor skill documents the
  pre-analyze-then-serve flow.
- The decompiler's success check is `result.getErrorMessage() == ""`, not a
  boolean.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Common install locations checked when neither GHIDRA_INSTALL_DIR nor the
# pack's config names one. Windows-style roots are included so the same
# detection runs on the Windows runner.
COMMON_INSTALL_DIRS = [
    # rolo's Mac (measured 2026-08-13): both arm64-native installs live here
    "/Users/rolo/Documents/obsidian/vibes/github/ghidra_12.1.2_PUBLIC",
    "/Users/rolo/Documents/obsidian/vibes/github/ghidra_11.3.2_PUBLIC",
    # course devcontainer
    "/ghidra",
    "/opt/ghidra",
    "/usr/share/ghidra",
    "C:/Program Files/ghidra",
]

DEFAULT_PROJECT_DIR = str(Path.home() / "ghidra-projects")


class GhidraProblem(Exception):
    """An actionable error: the message always says what to do next."""


def install_problem(root: Path) -> Optional[str]:
    """Why `root` is not a usable Ghidra install, or None when it is.

    Detection is by effect: the version file parses, the headless analyzer
    is executable, and the decompiler native exists for this platform.
    """
    props = root / "Ghidra" / "application.properties"
    if not props.is_file():
        return f"{root} has no Ghidra/application.properties"
    analyze = root / "support" / "analyzeHeadless"
    if not analyze.is_file():
        return f"{root} has no support/analyzeHeadless"
    plat = _platform_dir()
    decompile = root / "Ghidra" / "Features" / "Decompiler" / "os" / plat / "decompile"
    if not decompile.is_file():
        return f"{root} has no Decompiler/os/{plat}/decompile for this platform"
    return None


def _platform_dir() -> str:
    macos = sys.platform == "darwin"
    windows = os.name == "nt"
    arch = "x86_64" if sys.maxsize > 2**32 else "x86"
    import platform

    machine = platform.machine().lower()
    if macos:
        return "mac_arm_64" if machine in ("arm64", "aarch64") else "mac_x86_64"
    if windows:
        return "win_x86_64" if machine in ("amd64", "x86_64", "arm64") else "win_x86"
    return "linux_arm64" if machine in ("arm64", "aarch64") else "linux_x86_64"


def detect_install(explicit: str = "", env: Optional[dict] = None) -> str:
    """Resolve the Ghidra install dir: explicit > env > common locations.

    Returns the path, or raises GhidraProblem with the exact remedy.
    """
    env = env if env is not None else os.environ
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if env.get("GHIDRA_INSTALL_DIR"):
        candidates.append(env["GHIDRA_INSTALL_DIR"])
    candidates.extend(COMMON_INSTALL_DIRS)

    problems: list[str] = []
    for cand in candidates:
        if not cand:
            continue
        root = Path(cand).expanduser()
        why = install_problem(root)
        if why is None:
            return str(root)
        problems.append(f"  {cand}: {why}")
    raise GhidraProblem(
        "no usable Ghidra install found.\n"
        "Checked:\n" + "\n".join(problems) + "\n"
        "Fix: set the pack config key (halo pack config halo-re ghidra_install_dir <path>) "
        "or the GHIDRA_INSTALL_DIR env var to a Ghidra install folder (it holds "
        "Ghidra/application.properties). Ghidra itself is never bundled with this pack."
    )


def resolve_project_dir(explicit: str = "") -> str:
    """The Ghidra project dir; never one whose path elements start with '.'."""
    path = Path(explicit or DEFAULT_PROJECT_DIR).expanduser()
    for part in path.parts:
        if part.startswith(".") and part not in (".", ".."):
            raise GhidraProblem(
                f"project dir {path} has a dot-prefixed element; Ghidra refuses those "
                f"(IllegalArgumentException: Path element starting with '.' is not permitted). "
                f"Use a plain path like {DEFAULT_PROJECT_DIR}."
            )
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


class AnalysisSession:
    """One open Ghidra project and the binaries imported into it.

    Every tool call reads from here; nothing is re-opened per call. Mutating
    project operations (delete/rename/save) are deliberately absent from the
    surface -- the server is read-only by construction apart from `open`,
    which exists because importing the target you were pointed at IS the
    workflow (it is expensive; the skills say to confirm the target first).
    """

    def __init__(self, install_dir: str, project_dir: str, project_name: str = "halo-re"):
        os.environ["GHIDRA_INSTALL_DIR"] = install_dir  # BEFORE pyghidra.start()
        try:
            import pyghidra  # noqa: WPS433 (deliberate late import)
        except ImportError as exc:
            raise GhidraProblem(
                f"pyghidra is not importable from this Python ({sys.executable}): {exc}\n"
                "Fix: install the deps into the Python Halo runs the pack with, e.g.\n"
                '  python -m pip install pyghidra "mcp>=1.2,<2"\n'
                "The doctor skill (halo-re:ghidra-doctor) walks through this."
            ) from exc
        pyghidra.start(False)
        from ghidra.base.project import GhidraProject  # type: ignore

        self._GhidraProject = GhidraProject
        self.project_dir = project_dir
        self.project_name = project_name
        # The same open/create decision pyghidra's own core makes (measured on
        # 12.1.2: the 3-arg openProject(path, name, True) still throws
        # NotFoundException on a fresh project, so decide via ProjectLocator).
        from ghidra.framework.model import ProjectLocator  # type: ignore

        if ProjectLocator(project_dir, project_name).exists():
            self.project = GhidraProject.openProject(project_dir, project_name, True)
        else:
            Path(project_dir).mkdir(parents=True, exist_ok=True)
            self.project = GhidraProject.createProject(project_dir, project_name, False)
        self.programs: dict = {}      # display name -> ghidra Program
        self.decompilers: dict = {}   # display name -> DecompInterface

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        for dec in self.decompilers.values():
            try:
                dec.dispose()
            except Exception:
                pass
        try:
            self.project.close()
        except Exception:
            pass

    # -- opening binaries --------------------------------------------------

    def open(self, binary_path: str) -> dict:
        """Import (and analyze, first time only) a binary into the project.

        Follows pyghidra's own flow: reuse a program already in the project
        (openProgram), else importProgram + analyzeAll + save. Analysis runs
        ONLY when Ghidra says the program is unanalyzed, so a project that was
        pre-analyzed (the two-stage start) opens fast.
        """
        path = Path(binary_path).expanduser()
        if not path.is_file():
            raise GhidraProblem(f"no such binary: {path}")
        existing = self.find(path.name)
        if existing is not None:
            return {"status": "already-open", "binary": existing}

        name = path.name
        program = None
        if self.project.getRootFolder().getFile(name):
            program = self.project.openProgram("/", name, False)
        if program is None:
            from java.io import File  # type: ignore

            program = self.project.importProgram(File(str(path)))
            if program is None:
                raise GhidraProblem(f"Ghidra failed to import {path} (no loader accepted it)")
            self._analyze(program)
            self.project.saveAs(program, "/", name, True)
        self.programs[name] = program
        self._attach(name)
        return {
            "status": "opened",
            "binary": name,
            "note": "first open runs full Ghidra analysis (minutes for big binaries); later opens are fast",
        }

    def _analyze(self, program) -> None:
        """Run full analysis on a freshly imported program.

        Do NOT gate on GhidraProgramUtilities.shouldAskToAnalyze: on Ghidra
        12.1.2 a fresh importProgram already reports shouldAsk=False while
        analysis is still incomplete (measured: 5 functions before
        analyzeAll, 7 after, on a 3-function test binary). This method runs
        only on the fresh-import path, so the gate bought nothing.
        """
        from ghidra.program.util import GhidraProgramUtilities  # type: ignore
        from ghidra.app.script import GhidraScriptUtil  # type: ignore
        from ghidra.program.flatapi import FlatProgramAPI  # type: ignore

        GhidraScriptUtil.acquireBundleHostReference()
        try:
            FlatProgramAPI(program).analyzeAll(program)
            GhidraProgramUtilities.markProgramAnalyzed(program)
        finally:
            GhidraScriptUtil.releaseBundleHostReference()

    def _display_name(self, program, fallback: str) -> str:
        try:
            return str(program.getName())
        except Exception:
            return fallback

    def _attach(self, name: str) -> None:
        from ghidra.app.decompiler import DecompInterface  # type: ignore

        dec = DecompInterface()
        dec.openProgram(self.programs[name])
        self.decompilers[name] = dec

    def find(self, name: str) -> Optional[str]:
        """Resolve a user-supplied binary name against open programs.

        Project binary names carry a -<hash> suffix, so prefix matching is
        the rule; exact match wins first.
        """
        if name in self.programs:
            return name
        low = name.lower()
        for known in self.programs:
            if known.lower().startswith(low):
                return known
        return None

    def require(self, name: Optional[str]) -> tuple:
        """(name, program) for `name`, or the only open binary when None."""
        if name is None:
            if not self.programs:
                raise GhidraProblem(
                    "no binary is open. Call open_binary with the target path first, "
                    "or list_binaries to see what is already in the project."
                )
            only = next(iter(self.programs))
            return only, self.programs[only]
        resolved = self.find(name)
        if resolved is None:
            open_names = ", ".join(sorted(self.programs)) or "none"
            raise GhidraProblem(
                f"no open binary matches {name!r}. Open binaries: {open_names}. "
                "Names carry a -<hash> suffix; a prefix of the file name is enough."
            )
        return resolved, self.programs[resolved]

    # -- decompilation -----------------------------------------------------

    def decompile(self, binary: Optional[str], name_or_address: str, max_lines: int = 400) -> dict:
        _, program = self.require(binary)
        func = self._find_function(program, name_or_address)
        if func is None:
            raise GhidraProblem(
                f"no function matches {name_or_address!r}. Use search_functions "
                "for candidates first (substring match)."
            )
        dec = self.decompilers[self._name_of(program)]
        result = dec.decompileFunction(func, 60, None)
        if result.getErrorMessage() != "":  # the measured success check
            raise GhidraProblem(f"decompilation failed: {result.getErrorMessage()}")
        code = str(result.decompiledFunction.getC())
        lines = code.splitlines()
        if len(lines) > max_lines:
            code = "\n".join(lines[:max_lines]) + f"\n/* ... truncated at {max_lines} lines of {len(lines)}; raise max_lines for more */"
        return {
            "status": "ok",
            "name": str(func.getName()),
            "entry_point": str(func.getEntryPoint()),
            "signature": str(result.decompiledFunction.getSignature()),
            "code": code,
        }

    def _find_function(self, program, name_or_address: str):
        # address first (0x...), then exact name, then unique substring
        fm = program.getFunctionManager()
        try:
            addr = self._to_addr(program, name_or_address)
            if addr is not None:
                fn = fm.getFunctionAt(addr)
                if fn is not None:
                    return fn
        except Exception:
            pass
        low = name_or_address.lower()
        # exact name first (jpype cannot call FunctionManager.getFunction(String)
        # on this build -- measured; iterate instead)
        matches = [f for f in fm.getFunctions(True) if low == str(f.getName()).lower()]
        if not matches:
            matches = [f for f in fm.getFunctions(True) if low in str(f.getName()).lower()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            names = ", ".join(str(f.getName()) for f in matches[:10])
            raise GhidraProblem(f"{name_or_address!r} is ambiguous ({len(matches)} matches): {names}")
        return None

    def _name_of(self, program) -> str:
        for name, prog in self.programs.items():
            if prog is program:
                return name
        return str(program.getName())

    def _to_addr(self, program, text: str):
        try:
            from ghidra.program.model.address import AddressFactory  # noqa: F401

            factory = program.getAddressFactory()
            addr = factory.getAddress(text)
            if addr is None and text.lower().startswith("0x"):
                addr = factory.getAddress(text)
            return addr
        except Exception:
            return None
