import asyncio
import logging
import sys

from plugins.ping.plugin import handle_ping
from plugins.ping.plugin import manifest as ping_manifest
from zxtg.core.kernel.registry import registry
from zxtg.core.platform.console import ConsoleAdapter
from zxtg.core.services.db import close_db, init_db
from zxtg.logging_setup import setup_logging

logger = logging.getLogger("zxtg.main")


async def async_main() -> int:
    """Main asynchronous entry point for ZX-TG (M0 console mode)."""
    setup_logging()
    logger.info("Starting ZX-TG (M0)...")

    # Initialize SQLite database
    await init_db()

    # Register default ping plugin
    registry.register(ping_manifest, {"ping": handle_ping})
    logger.info("Registered plugin: %s (%s)", ping_manifest.name, ping_manifest.key)

    # Run console adapter
    adapter = ConsoleAdapter()
    await adapter.start()

    line = sys.stdin.readline()
    if line:
        await adapter.process_line(line)

    await adapter.stop()
    await close_db()
    return 0


def main() -> None:
    """Synchronous CLI entry point."""
    try:
        sys.exit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
