import logging
from pathlib import Path
from typing import Any

import aiosqlite
from tortoise import Tortoise

from zxtg.config import config
from zxtg.models.migration_record import MigrationRecord

logger = logging.getLogger("zxtg.services.db")


async def init_db(db_path: str | None = None, generate_schemas: bool = True) -> None:
    """Initialize Tortoise ORM with SQLite backend, WAL mode, and busy_timeout (FR-DATA-01, FR-DATA-02)."""
    target_path = db_path or config.DB_PATH
    if target_path == ":memory:":
        db_url = "sqlite://:memory:"
        logger.info("Initializing in-memory database")
    else:
        db_file = Path(target_path).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite://{db_file}"
        logger.info("Initializing database at: %s", db_file)

    await Tortoise.init(
        db_url=db_url,
        modules={"models": ["zxtg.models"]},
    )

    conn = Tortoise.get_connection("default")
    # For file-backed SQLite, enable WAL mode (FR-DATA-01)
    if target_path != ":memory:":
        await conn.execute_query("PRAGMA journal_mode=WAL;")
    # Set busy_timeout >= 5000 ms (FR-DATA-02)
    await conn.execute_query("PRAGMA busy_timeout=5000;")

    if generate_schemas:
        logger.debug("Generating database schemas...")
        await Tortoise.generate_schemas()

    # Read persisted global configurations back into config_service (FR-CFG-01, NEXT-TASK-M4FIX §1)
    from zxtg.core.services.config_service import config_service

    await config_service.load_global()

    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Close active database connections gracefully (FR-CORE-06)."""
    logger.info("Closing database connections...")
    await Tortoise.close_connections()
    from zxtg.core.services.config_service import config_service

    config_service._global_configs.clear()
    logger.info("Database connections closed")


async def get_db_pragmas() -> dict[str, Any]:
    """Retrieve active PRAGMA journal_mode and busy_timeout (FR-DATA-01, FR-DATA-02)."""
    conn = Tortoise.get_connection("default")
    _, jm = await conn.execute_query("PRAGMA journal_mode;")
    _, bt = await conn.execute_query("PRAGMA busy_timeout;")
    journal_mode = dict(jm[0]).get("journal_mode") if jm else ""
    busy_timeout = dict(bt[0]).get("timeout") if bt else 0
    return {
        "journal_mode": str(journal_mode),
        "busy_timeout": int(busy_timeout),
    }


async def check_db_integrity(db_path: str | None = None) -> tuple[bool, str]:
    """Check database file integrity using SQLite PRAGMA integrity_check (FR-DATA-09).

    Returns (is_healthy: bool, diagnosis_message: str).
    """
    target_path = db_path or config.DB_PATH
    if target_path == ":memory:":
        return True, "ok (in-memory)"

    db_file = Path(target_path).resolve()
    if not db_file.exists():
        return False, f"Database file does not exist: {db_file}"

    try:
        async with aiosqlite.connect(str(db_file)) as conn:
            async with conn.execute("PRAGMA integrity_check;") as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "ok":
                    return True, "ok"
                err_text = row[0] if row else "Unknown integrity failure"
                return False, f"Database corruption detected: {err_text}"
    except Exception as exc:
        return False, f"Database file corruption or access error: {exc}"


async def record_migration(plugin_key: str, version: str) -> MigrationRecord:
    """Record an applied migration version for core or a plugin (FR-PLG-10)."""
    record, created = await MigrationRecord.get_or_create(
        plugin_key=plugin_key,
        version=version,
    )
    if created:
        logger.info("Recorded migration for %s version %s", plugin_key, version)
    else:
        logger.debug("Migration for %s version %s already recorded", plugin_key, version)
    return record


async def run_explicit_migration(
    plugin_key: str, version: str, script_fn: Any = None
) -> bool:
    """Execute explicit migration script without runtime auto-ALTER (FR-DATA-05)."""
    existing = await MigrationRecord.filter(plugin_key=plugin_key, version=version).first()
    if existing:
        logger.debug("Migration %s:%s already applied", plugin_key, version)
        return False
    if script_fn and callable(script_fn):
        await script_fn()
    await record_migration(plugin_key, version)
    return True


async def run_migrations(
    plugin_key: str = "core", target_version: str = "0.1.0"
) -> list[str]:
    """Run pending migrations for core or plugins."""
    applied: list[str] = []
    existing = await MigrationRecord.filter(plugin_key=plugin_key, version=target_version).first()
    if not existing:
        await record_migration(plugin_key, target_version)
        applied.append(target_version)
    return applied
