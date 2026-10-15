import logging
from pathlib import Path
from tortoise import Tortoise

from zxtg.config import config
from zxtg.models.migration_record import MigrationRecord

logger = logging.getLogger("zxtg.services.db")


async def init_db(db_path: str | None = None, generate_schemas: bool = True) -> None:
    """Initialize Tortoise ORM with SQLite backend (D4, SRS v1.0 §8)."""
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

    if generate_schemas:
        logger.debug("Generating database schemas...")
        await Tortoise.generate_schemas()
    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Close active database connections gracefully (FR-CORE-06)."""
    logger.info("Closing database connections...")
    await Tortoise.close_connections()
    logger.info("Database connections closed")


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


async def run_migrations(plugin_key: str = "core", target_version: str = "0.1.0") -> list[str]:
    """Run pending migrations for core or plugins."""
    applied: list[str] = []
    existing = await MigrationRecord.filter(plugin_key=plugin_key, version=target_version).first()
    if not existing:
        await record_migration(plugin_key, target_version)
        applied.append(target_version)
    return applied
