# GHIDRA-NOTES.md — every Ghidra trap in this pack, measured

Each of these was hit for real, not read about. Sources: the agentic-RE
course stack (2026-08), the halo-hacker Ghidra bake (2026-08-13), and this
pack's own smoke tests against Ghidra 12.1.2 on arm64 macOS (2026-10-25).

## Install detection

- **There is no binary named `ghidra`.** The release ships `ghidraRun` and
  `support/analyzeHeadless`, and a zip-extract install puts neither on
  PATH. `which ghidra` reports "not installed" on a box holding two
  complete installs. Detect by effect: `Ghidra/application.properties`
  parses + `support/analyzeHeadless` is executable + the decompiler native
  exists at `Ghidra/Features/Decompiler/os/<platform>/decompile`.
- **Platform directory names**: `mac_arm_64`, `mac_x86_64`, `linux_x86_64`,
  `linux_arm64`, `win_x86_64` (mac_arm_64, not mac_arm — measured).

## Projects and paths

- **Ghidra refuses any path element beginning with a dot** —
  `IllegalArgumentException: Path element starting with '.' is not
  permitted`. Projects never live under `~/.local/share` or `~/.halo`;
  the pack defaults to `~/ghidra-projects`.
- **`GHIDRA_INSTALL_DIR` must be in the environment BEFORE
  `pyghidra.start()`** — a subprocess that inherits a clean env fails
  silently. The server sets it from `detect_install()` first.
- **One process locks one project.** A second `GhidraProject.openProject`
  on the same project raises `LockException` — the server holds ONE
  session; tests must close before reopening.

## Import and analysis (Ghidra 12.1.2 + pyghidra 3.2, measured)

- `GhidraProject.openProject(path, name, True)` **still throws
  NotFoundException on a fresh project** despite the create flag. Decide
  via `ProjectLocator(dir, name).exists()` (from `ghidra.framework.model`),
  then `openProject` or `createProject(dir, name, False)`.
- `importProgram` needs a `java.io.File`, not a str (jpype does not
  auto-convert).
- **A fresh import reports `shouldAskToAnalyze == False` while analysis is
  still incomplete** (5 functions before `analyzeAll`, 7 after, on a
  3-function test binary). Never gate analysis on that flag on the import
  path; run `FlatProgramAPI(program).analyzeAll(program)` +
  `markProgramAnalyzed` with the bundle-host reference held.
- `FunctionManager.getFunction(String)` is not callable through jpype on
  this build — iterate `getFunctions(True)` and match names in Python.
- `SleighLanguage` has no `getEndian()` — the language *description*
  carries the endian.
- Analysis time: ~2 s for a small arm64 binary; minutes for drivers;
  **~40 min + RAM blowout for a 20k-function dylib** (use the Mach-O
  LIEF path for those). Decompiler success check is
  `result.getErrorMessage() == ""`, not a boolean.

## Serving analysis to agents

- **Two-stage start**: analyzing while a client waits times out the
  client's handshake (MCPO dies during `--wait-for-analysis`). Analyze
  once into a persistent project standalone, then serve — reopen from the
  cached project is ~1.6 s.
- Binary names in a Ghidra project can carry a `-<hash>` suffix; prefix
  matching is the rule.
- **Read-only by construction**: the tool surface exposes no
  rename/delete/save; `open_binary` (expensive, first-time analysis) is
  the only mutating call, and the skills confirm the target before it.
- FastMCP builds each tool's schema from `inspect.signature`: a
  `*args/**kwargs` wrapper publishes a schema demanding literal
  `args`/`kwargs` (measured in the smoke test) — use `functools.wraps`.

## The on-demand installer (measured 2026-10-25, live downloads)

- **Ghidra 12.2 ships no macOS decompiler natives at all** — `Decompiler/os/`
  holds only `linux_x86_64` and `win_x86_64`. Same for 12.1.3 and 12.1.4:
  **macOS natives stopped after 12.1.2**. The installer walks back through
  previous releases until one verifies by effect for the running platform.
- **Release zips do not preserve the executable bit.** The extracted
  `Decompiler/os/<plat>/decompile` is `-rw-r--r--`, and pyghidra then fails
  decompilation with `decompiledFunction=None` AND an **empty** error
  message — the least diagnosable failure in the whole stack. The installer
  chmods the launchers and every native under `Ghidra/Features/*/os/*`.
- REA's release zip is a **single FILE** (`REA-<ver>.exe`, ~98 MB,
  Windows), not a directory — an extractor that assumes a top-level
  directory crashes on it.
