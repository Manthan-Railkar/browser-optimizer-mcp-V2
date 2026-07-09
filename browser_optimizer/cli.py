"""
Browser Optimizer MCP — Command-Line Interface
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Provides the `browser-optimizer` command installed by pip.

Commands:
  install   Auto-install Playwright browsers and configure MCP clients
  doctor    Diagnose the local installation
  start     Start the MCP server (stdio mode)
  version   Print the current version
"""

import sys


# ─────────────────────────────────────────────────────────────
# Colour helpers (zero dependencies)
# ─────────────────────────────────────────────────────────────
class _C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"


BANNER = f"""
{_C.BOLD}{_C.CYAN}╔══════════════════════════════════════════╗
║      Browser Optimizer MCP  v{{version}}     ║
║  Reduce LLM token costs by up to 98%    ║
╚══════════════════════════════════════════╝{_C.RESET}
"""


def _print_banner() -> None:
    from browser_optimizer import __version__
    print(BANNER.format(version=__version__))


def _divider() -> None:
    print(f"{_C.DIM}{'─' * 46}{_C.RESET}")


# ─────────────────────────────────────────────────────────────
# install
# ─────────────────────────────────────────────────────────────
def cmd_install() -> None:
    _print_banner()
    print(f"{_C.BOLD}Running installation wizard…{_C.RESET}\n")
    _divider()

    from browser_optimizer import installer

    steps = [
        ("Checking Python version",          installer.check_python_version),
        ("Installing Playwright browsers",   installer.install_playwright_browsers),
        ("Configuring Claude Desktop",       installer.detect_and_configure_claude),
        ("Configuring Antigravity IDE",      installer.detect_and_configure_antigravity),
        ("Verifying installation",           installer.verify_installation),
    ]

    all_ok = True
    for label, fn in steps:
        print(f"\n{_C.BOLD}▶  {label}{_C.RESET}")
        result = fn()
        if result is False:
            all_ok = False

    print()
    _divider()
    installer.print_cursor_instructions()
    _divider()
    print()

    if all_ok:
        print(
            f"{_C.GREEN}{_C.BOLD}✨  Installation complete!{_C.RESET}\n\n"
            f"    Start the server:   {_C.CYAN}browser-optimizer start{_C.RESET}\n"
            f"    Check health:       {_C.CYAN}browser-optimizer doctor{_C.RESET}\n"
        )
    else:
        print(
            f"{_C.YELLOW}{_C.BOLD}⚠️   Installation finished with warnings.{_C.RESET}\n"
            f"    Review the items marked ❌ above and re-run {_C.CYAN}browser-optimizer install{_C.RESET}.\n"
        )


# ─────────────────────────────────────────────────────────────
# doctor
# ─────────────────────────────────────────────────────────────
def cmd_doctor() -> None:
    _print_banner()
    print(f"{_C.BOLD}Running diagnostics…{_C.RESET}\n")
    _divider()

    import importlib
    import platform

    def _ok(msg):  print(f"  \033[92m✅\033[0m  {msg}")
    def _fail(msg): print(f"  \033[91m❌\033[0m  {msg}")
    def _warn(msg): print(f"  \033[93m⚠️ \033[0m  {msg}")

    # 1. Python version
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}.{sys.version_info[2]}"
    if major == 3 and minor >= 11:
        _ok(f"Python {ver}")
    else:
        _fail(f"Python {ver} — need ≥ 3.11")

    # 2. Core package imports
    for pkg in ["mcp", "playwright", "pydantic", "loguru", "xxhash", "cachetools"]:
        try:
            importlib.import_module(pkg)
            _ok(f"Package '{pkg}' available")
        except ImportError:
            _fail(f"Package '{pkg}' not installed — run: pip install {pkg}")

    # 3. browser_optimizer itself
    try:
        import browser_optimizer
        _ok(f"browser_optimizer package v{browser_optimizer.__version__}")
    except ImportError as exc:
        _fail(f"browser_optimizer import error: {exc}")

    # 4. MCP config files
    from pathlib import Path
    from browser_optimizer.installer import _antigravity_config_path, _claude_config_path

    claude_path = _claude_config_path()
    if claude_path and claude_path.exists():
        _ok(f"Claude Desktop config found: {claude_path}")
    elif claude_path:
        _warn(f"Claude Desktop config not found: {claude_path}")
    else:
        _warn("Claude Desktop config path unknown on this OS")

    ag_path = _antigravity_config_path()
    if ag_path.exists():
        _ok(f"Antigravity IDE config found: {ag_path}")
    else:
        _warn(f"Antigravity IDE config not found: {ag_path}")

    # 5. Platform info
    print()
    _divider()
    print(
        f"\n  Platform: {platform.system()} {platform.release()} "
        f"({platform.machine()})\n"
        f"  Python:   {sys.executable}\n"
    )


# ─────────────────────────────────────────────────────────────
# start
# ─────────────────────────────────────────────────────────────
def cmd_start() -> None:
    _print_banner()
    print(f"{_C.BOLD}Starting Browser Optimizer MCP server…{_C.RESET}")
    print(f"{_C.DIM}(stdio mode — connect your MCP client){_C.RESET}\n")

    import asyncio
    from browser_optimizer.server.main import main
    asyncio.run(main())


# ─────────────────────────────────────────────────────────────
# version
# ─────────────────────────────────────────────────────────────
def cmd_version() -> None:
    from browser_optimizer import __version__
    print(f"browser-optimizer-mcp {__version__}")


# ─────────────────────────────────────────────────────────────
# help
# ─────────────────────────────────────────────────────────────
USAGE = f"""
{_C.BOLD}Usage:{_C.RESET}
  browser-optimizer <command>

{_C.BOLD}Commands:{_C.RESET}
  {_C.CYAN}install{_C.RESET}   Install Playwright browsers & auto-configure MCP clients
  {_C.CYAN}doctor{_C.RESET}    Diagnose your local installation
  {_C.CYAN}start{_C.RESET}     Start the MCP server (stdio mode)
  {_C.CYAN}version{_C.RESET}   Show the current version

{_C.BOLD}Examples:{_C.RESET}
  pip install browser-optimizer-mcp
  browser-optimizer install
  browser-optimizer start
"""


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────
def main() -> None:
    if len(sys.argv) < 2:
        _print_banner()
        print(USAGE)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "install":
        cmd_install()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "start":
        cmd_start()
    elif cmd in ("version", "--version", "-v"):
        cmd_version()
    elif cmd in ("help", "--help", "-h"):
        _print_banner()
        print(USAGE)
    else:
        print(f"\n  {_C.RED}Unknown command: '{cmd}'{_C.RESET}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
