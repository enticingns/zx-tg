#!/usr/bin/env python3
"""Non-interactive smoke test for ZX-TG M0.

Validates that:
1. Subprocess execution 'echo ping | python -m zxtg' executes cleanly (rc=0).
2. The output contains 'pong'.
3. In-process pipeline directly delivers 'pong'.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from plugins.ping.plugin import handle_ping
from plugins.ping.plugin import manifest as ping_manifest
from zxtg.core.kernel.registry import registry
from zxtg.core.platform.console import ConsoleAdapter
from zxtg.core.services.db import close_db, init_db


async def smoke_in_process() -> None:
    """Run in-process pipeline test."""
    await init_db(db_path=":memory:")
    registry.register(ping_manifest, {"ping": handle_ping})

    adapter = ConsoleAdapter()
    await adapter.start()
    replies = await adapter.process_line("ping")
    await adapter.stop()
    await close_db()

    assert any("pong" in r.lower() for r in replies), f"Expected 'pong' in replies, got: {replies}"
    print("[SMOKE-M0] In-process check: PASS (received 'pong')")


def smoke_subprocess() -> None:
    """Run CLI subprocess test: echo ping | python -m zxtg."""
    cmd = [sys.executable, "-m", "zxtg"]
    proc = subprocess.run(
        cmd,
        input="ping\n",
        text=True,
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    combined = proc.stdout + proc.stderr
    print(f"[SMOKE-M0] Subprocess exit code: {proc.returncode}")
    print(f"[SMOKE-M0] Output:\n{combined.strip()}")

    assert proc.returncode == 0, f"Expected rc=0, got {proc.returncode}"
    assert "pong" in combined.lower(), f"Expected 'pong' in output, got: {combined}"
    print("[SMOKE-M0] Subprocess check: PASS (rc=0 and contains 'pong')")


def main() -> None:
    print("=== Starting ZX-TG M0 Smoke Test ===")
    asyncio.run(smoke_in_process())
    smoke_subprocess()
    print("=== ZX-TG M0 Smoke Test: ALL PASS ===")


if __name__ == "__main__":
    main()
