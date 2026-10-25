#!/usr/bin/env python3
"""halo-re pack -- on-demand tool installer.

Downloads and installs the tools this pack drives, from their official
GitHub releases, on first use:

  ghidra   NationalSecurityAgency/ghidra  (Apache-2.0, ~570 MB zip)
  rea      ReverseEngineer-Anything/REA-Github (MIT, ~40 MB zip)

Usage:
  install_tools.py --tool ghidra --check          what the latest release is, no download
  install_tools.py --tool ghidra --yes            download + install + verify + persist the path
  install_tools.py --tool rea --check
  install_tools.py --tool rea --yes [--version 6.3.0] [--tools-dir DIR]

Behavior contract (each rule measured or deliberate):
- NEVER downloads without an explicit yes: --yes, or a y/N answer on a tty.
  Non-interactive without --yes prints the exact command to run and exits 1.
- Installs land in the tools dir (default ~/halo-re-tools, overridable via
  the pack config key `tools_dir`); the zip is cached under <tools>/downloads.
- Installs are verified BY EFFECT (ghidra: application.properties +
  analyzeHeadless + the platform decompiler native -- exactly what
  ghidra_core.detect_install checks), never by "the download finished".
- On success the path is persisted: `halo config set
  packs.settings.halo-re.<key> <path>` (ghidra_install_dir / rea_dir), so the
  pack's MCP server and the doctor find it on every later run. When the
  halo CLI is not reachable the exact command is printed to run by hand.
- Ghidra needs a JDK (21+); the script checks `java -version` first and
  prints the remedy instead of installing a broken toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

PACK_ROOT = Path(__file__).resolve().parents[3]  # .../pack
TOOLS = {
    "ghidra": {
        "repo": "NationalSecurityAgency/ghidra",
        "asset_re": r"^ghidra_[\w.]+_PUBLIC_[\d]+\.zip$",
        "config_key": "ghidra_install_dir",
        "verify": "effect",   # application.properties + analyzeHeadless + decompiler native
    },
    "rea": {
        "repo": "ReverseEngineer-Anything/REA-Github",
        "asset_re": r"^REA-[\w.]+\.zip$",
        "config_key": "rea_dir",
        "verify": "listing",  # top-level listing (REA has no install manifest we can check)
    },
}

API = "https://api.github.com/repos/{repo}/releases/{which}"


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _get_json(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/vnd.github+json"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def latest_release(repo: str, tag: str | None) -> tuple:
    which = f"tags/{tag}" if tag else "latest"
    data = _get_json(API.format(repo=repo, which=which))
    if "tag_name" not in data:
        die(f"no release found for {repo} ({data.get('message', data)})")
    return data["tag_name"], data.get("assets", [])


def pick_asset(assets: list, pattern: str) -> dict:
    rx = re.compile(pattern)
    for asset in assets:
        if rx.match(asset.get("name", "")):
            return asset
    die(f"no asset matches {pattern!r} in the release")


def default_tools_dir() -> Path:
    """The pack config key `tools_dir` when halo is reachable, else ~/halo-re-tools."""
    try:
        out = subprocess.run(
            ["halo", "config", "get", "packs.settings.halo-re.tools_dir"],
            capture_output=True, text=True, timeout=30,
        )
        value = out.stdout.strip().strip('"')
        if out.returncode == 0 and value and value not in ("null", ""):
            return Path(value).expanduser()
    except Exception:
        pass
    return Path.home() / "halo-re-tools"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url)
    with urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = 100 * done // total
                sys.stdout.write(f"\r  downloading... {done/1e6:.0f}/{total/1e6:.0f} MB ({pct}%)")
                sys.stdout.flush()
    print()


def extract(zip_path: Path, tools_dir: Path) -> Path:
    """Extract and return the top-level path the zip created.

    Some releases zip a DIRECTORY (Ghidra: ghidra_12.2_PUBLIC_.../), some a
    single FILE (REA: REA-6.3.0.exe -- measured). Handle both; a previous
    install of the same name is replaced."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.strip("/")]
        if not names:
            die("zip is empty")
        tops = {n.split("/")[0] for n in names}
        if len(tops) != 1:
            die(f"zip has {len(tops)} top-level entries, expected 1")
        top = next(iter(tops))
        target = tools_dir / top
        tools_dir.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        zf.extractall(tools_dir)
    return target


def fix_exec_bits(root: Path) -> None:
    """chmod +x the launchers and natives: release zips do NOT preserve the
    executable bit (measured: the decompiler native extracts as -rw-r--r--,
    and pyghidra then fails decompilation with decompiledFunction=None and
    an EMPTY error message)."""
    import stat

    targets = [root / "support" / "analyzeHeadless", root / "ghidraRun"]
    targets += [root / "server" / n for n in ("svrAdmin", "svrInstall", "svrUninstall")]
    for feature in (root / "Ghidra" / "Features").glob("*"):
        for osdir in (feature / "os").glob("*"):
            if osdir.is_dir():
                targets += [p for p in osdir.iterdir() if p.is_file()]
    for t in targets:
        try:
            if t.is_file():
                t.chmod(t.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass


def verify_ghidra(root: Path) -> str:
    """By-effect verification. Returns '' on success, or the problem;
    a problem naming the platform decompiler means the RELEASE lacks
    natives for this OS (measured: Ghidra 12.2 ships no macOS decompiler),
    which the caller turns into a fallback to an older release."""
    sys.path.insert(0, str(PACK_ROOT / "mcp"))
    from ghidra_core import install_problem  # noqa: E402

    why = install_problem(root)
    if why:
        return why
    props = (root / "Ghidra" / "application.properties").read_text(errors="replace")
    version = next((ln.split("=", 1)[1].strip() for ln in props.splitlines()
                    if ln.startswith("application.version=")), "?")
    print(f"  verified by effect: Ghidra {version} at {root}")
    return ""


def platform_native_missing(why: str) -> bool:
    return "decompile" in why and "no Decompiler/os/" in why


def previous_release_tags(repo: str, before: str, count: int = 3) -> list:
    data = _get_json(f"https://api.github.com/repos/{repo}/releases?per_page=30")
    if not isinstance(data, list):
        return []
    tags = [r.get("tag_name") for r in data if r.get("tag_name") and r.get("assets")]
    try:
        idx = tags.index(before)
        return tags[idx + 1 : idx + 1 + count]
    except ValueError:
        return tags[:count]


def verify_listing(root: Path) -> None:
    if root.is_file():
        # a single-file release (measured: REA ships REA-<ver>.exe)
        size = root.stat().st_size
        if size < 100_000:
            die(f"extracted {root} is only {size} bytes -- not a real tool")
        print(f"  extracted single file: {root} ({size/1e6:.1f} MB)")
        return
    entries = sorted(p.name for p in root.iterdir())
    if not entries:
        die(f"{root} is empty after extraction")
    print(f"  extracted {len(entries)} top-level entries: {', '.join(entries[:8])}"
          + (" ..." if len(entries) > 8 else ""))


def persist_config(key: str, value: str) -> None:
    setting = f"packs.settings.halo-re.{key}"
    try:
        out = subprocess.run(
            ["halo", "config", "set", setting, value],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            print(f"  persisted: halo config set {setting} {value}")
            return
        print(f"  halo config set failed: {out.stderr.strip()}", file=sys.stderr)
    except Exception as exc:
        print(f"  halo config set failed: {exc}", file=sys.stderr)
    print(f"  RUN BY HAND: halo config set {setting} {value}")


def check_java() -> None:
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=30)
        first = (out.stderr or out.stdout).splitlines()[0] if (out.stderr or out.stdout) else ""
    except Exception:
        first = ""
    m = re.search(r'version "(\d+)', first)
    if not m:
        print("  NOTE: no `java` on PATH. Ghidra needs a JDK 21+ (e.g. Temurin: "
              "https://adoptium.net). Install it before running analyzeHeadless.")
        return
    major = int(m.group(1))
    if major < 21:
        print(f"  NOTE: java {major} found; Ghidra needs 21+. Install Temurin 21+ "
              "(https://adoptium.net) or the decompiler will fail to launch.")
    else:
        print(f"  java {major} OK (Ghidra needs 21+)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--tool", required=True, choices=sorted(TOOLS))
    ap.add_argument("--check", action="store_true", help="show the latest release, download nothing")
    ap.add_argument("--yes", action="store_true", help="download without asking")
    ap.add_argument("--version", help="a specific release tag (default: latest)")
    ap.add_argument("--tools-dir", help="where installs land (default: pack config tools_dir, else ~/halo-re-tools)")
    args = ap.parse_args()

    spec = TOOLS[args.tool]
    tag, assets = latest_release(spec["repo"], args.version)
    asset = pick_asset(assets, spec["asset_re"])
    size_mb = asset["size"] / 1e6
    print(f"{args.tool}: release {tag} -> {asset['name']} ({size_mb:.0f} MB)")
    print(f"  {asset['browser_download_url']}")

    if args.tool == "ghidra":
        check_java()

    if args.check:
        print("  --check: stopping here, nothing downloaded")
        return 0

    if not args.yes:
        if sys.stdin.isatty():
            answer = input(f"  download and install {asset['name']} ({size_mb:.0f} MB)? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print("  declined, nothing downloaded")
                return 0
        else:
            die(f"non-interactive run needs --yes: install_tools.py --tool {args.tool} --yes")
            return 1

    tools_dir = Path(args.tools_dir).expanduser() if args.tools_dir else default_tools_dir()

    # Platform fallback: a release can ship no natives for this OS (measured:
    # Ghidra 12.2 ships no macOS decompiler). Walk back through the previous
    # releases until one verifies by effect, max 3 attempts.
    tried = [tag]
    while True:
        zip_path = tools_dir / "downloads" / asset["name"]
        if not zip_path.is_file():
            download(asset["browser_download_url"], zip_path)
        else:
            print(f"  using cached {zip_path}")
        root = extract(zip_path, tools_dir)

        if spec["verify"] == "effect":
            fix_exec_bits(root)
            why = verify_ghidra(root)
            if why and platform_native_missing(why) and args.tool == "ghidra":
                print(f"  release {tag} does not support this platform ({why}); "
                      "trying the previous release")
                shutil.rmtree(root, ignore_errors=True)
                zip_path.unlink(missing_ok=True)  # a zip without our natives is dead weight
                older = [t for t in previous_release_tags(spec["repo"], tag) if t not in tried]
                if not older:
                    die(f"no recent {spec['repo']} release ships decompiler natives for this "
                        "platform; keep your existing install or build from source")
                tag = older[0]
                tried.append(tag)
                _, assets = latest_release(spec["repo"], tag)
                asset = pick_asset(assets, spec["asset_re"])
                print(f"  falling back to release {tag} -> {asset['name']} "
                      f"({asset['size']/1e6:.0f} MB)")
                continue
            if why:
                die(f"extracted install fails the by-effect check: {why}")
        else:
            verify_listing(root)
        break

    persist_config(spec["config_key"], str(root))
    print(f"OK: {args.tool} installed at {root}; the pack now knows where it is")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
