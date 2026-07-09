"""
Browser Optimizer MCP — Installer Helper
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Handles post-install setup: Playwright browsers, MCP client auto-configuration.
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Colour helpers (no external deps)
# ─────────────────────────────────────────────────────────────
class _C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


def _ok(msg: str)   -> None: print(f"  {_C.GREEN}✅{_C.RESET}  {msg}")
def _warn(msg: str) -> None: print(f"  {_C.YELLOW}⚠️ {_C.RESET}  {msg}")
def _err(msg: str)  -> None: print(f"  {_C.RED}❌{_C.RESET}  {msg}")
def _info(msg: str) -> None: print(f"  {_C.CYAN}ℹ️ {_C.RESET}  {msg}")


# ─────────────────────────────────────────────────────────────
# MCP server entry — what gets written into client configs
# ─────────────────────────────────────────────────────────────
def _mcp_entry() -> dict:
    """Build the MCP config block that points to this installation."""
    python_exe = sys.executable
    return {
        "command": python_exe,
        "args": ["-m", "browser_optimizer.server.main"],
    }


# ─────────────────────────────────────────────────────────────
# Step 1 — Python version check
# ─────────────────────────────────────────────────────────────
def check_python_version() -> bool:
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info[2]}"
    if major == 3 and minor >= 11:
        _ok(f"Python {version_str} — meets requirement (≥ 3.11)")
        return True
    _err(f"Python {version_str} found — need Python 3.11 or newer.")
    return False


# ─────────────────────────────────────────────────────────────
# Step 2 — Playwright browser install
# ─────────────────────────────────────────────────────────────
def install_playwright_browsers() -> bool:
    _info("Installing Playwright browser binaries (chromium) …")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
        _ok("Playwright chromium installed successfully.")
        return True
    except subprocess.CalledProcessError as exc:
        _err(f"Playwright install failed:\n{exc.stderr.strip()}")
        return False
    except FileNotFoundError:
        _err("'playwright' module not found. Run: pip install playwright")
        return False


# ─────────────────────────────────────────────────────────────
# Generic JSON config merger
# ─────────────────────────────────────────────────────────────
def _merge_mcp_config(config_path: Path, server_key: str = "browser-optimizer") -> bool:
    """
    Read an existing MCP JSON config (or start fresh), inject our server entry
    under mcpServers.<server_key>, and write it back atomically.
    """
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)

        existing: dict = {}
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}

        existing.setdefault("mcpServers", {})[server_key] = _mcp_entry()

        with config_path.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        return True
    except Exception as exc:  # noqa: BLE001
        _err(f"Could not write {config_path}: {exc}")
        return False


# ─────────────────────────────────────────────────────────────
# Step 3 — Claude Desktop
# ─────────────────────────────────────────────────────────────
def _claude_config_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return None


def detect_and_configure_claude() -> bool:
    path = _claude_config_path()
    if path is None:
        _warn("Claude Desktop config path unknown on this OS — skipping.")
        return False

    if not path.parent.exists() and not any(
        Path.home().joinpath(p).exists()
        for p in [
            "Library/Application Support/Claude",
            "AppData/Roaming/Claude",
        ]
    ):
        _warn("Claude Desktop does not appear to be installed — skipping.")
        return False

    if _merge_mcp_config(path):
        _ok(f"Claude Desktop config updated:\n       {path}")
        return True
    return False


# ─────────────────────────────────────────────────────────────
# Step 4 — Antigravity IDE
# ─────────────────────────────────────────────────────────────
def _antigravity_config_path() -> Path:
    return Path.home() / ".gemini" / "config" / "mcp_config.json"


def detect_and_configure_antigravity() -> bool:
    path = _antigravity_config_path()

    if not path.parent.exists():
        _warn("Antigravity IDE config directory not found — skipping.")
        return False

    if _merge_mcp_config(path):
        _ok(f"Antigravity IDE config updated:\n       {path}")
        return True
    return False


# ─────────────────────────────────────────────────────────────
# Step 5 — Cursor (manual — no config-file API)
# ─────────────────────────────────────────────────────────────
def print_cursor_instructions() -> None:
    entry = _mcp_entry()
    _info("Cursor requires manual setup:")
    print(
        f"\n    {_C.BOLD}Settings → Features → MCP → + Add New MCP Server{_C.RESET}\n"
        f"      Name:    browser-optimizer\n"
        f"      Type:    command\n"
        f"      Command: {entry['command']} -m browser_optimizer.server.main\n"
    )


# ─────────────────────────────────────────────────────────────
# Step 6 — Verify installation
# ─────────────────────────────────────────────────────────────
def verify_installation() -> bool:
    try:
        import browser_optimizer  # noqa: F401
        from browser_optimizer.config.settings import settings  # noqa: F401
        _ok("browser_optimizer package imports correctly.")
        return True
    except ImportError as exc:
        _err(f"Import verification failed: {exc}")
        return False
