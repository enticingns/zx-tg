"""Static AST scanning to enforce architectural boundaries B1, B3, and B4 (NEXT-TASK-M0 §1.6)."""
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_all_imports(file_path: Path) -> list[str]:
    """Parse a python file into AST and return all imported module paths."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_b3_boundary_kernel_and_services_no_platform_imports():
    """B3: core/kernel and core/services must NOT import telegram/aiogram or platform libs."""
    forbidden_prefixes = (
        "telegram",
        "aiogram",
        "telethon",
        "pyrogram",
        "nonebot",
        "onebot",
        "zxtg.core.platform",
        "httpx",
    )

    targets = [
        PROJECT_ROOT / "src" / "zxtg" / "core" / "kernel",
        PROJECT_ROOT / "src" / "zxtg" / "core" / "services",
    ]

    scanned_files = 0
    for target_dir in targets:
        assert target_dir.exists(), f"Target directory {target_dir} must exist"
        for py_file in target_dir.rglob("*.py"):
            scanned_files += 1
            imports = get_all_imports(py_file)
            for imp in imports:
                for forbidden in forbidden_prefixes:
                    assert not (imp == forbidden or imp.startswith(f"{forbidden}.")), (
                        f"Boundary B3 VIOLATION in {py_file}: forbidden import '{imp}'"
                    )

    assert scanned_files > 0, "At least one kernel/services python file must be scanned"


def test_b1_boundary_plugins_no_platform_imports():
    """B1: plugins/ must NOT import core.platform or platform libs directly."""
    forbidden_prefixes = (
        "zxtg.core.platform",
        "core.platform",
        "telegram",
        "aiogram",
        "telethon",
        "pyrogram",
        "httpx",
    )

    plugins_dir = PROJECT_ROOT / "plugins"
    scanned_files = 0
    for py_file in plugins_dir.rglob("*.py"):
        scanned_files += 1
        imports = get_all_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_prefixes:
                assert not (imp == forbidden or imp.startswith(f"{forbidden}.")), (
                    f"Boundary B1 VIOLATION in {py_file}: forbidden import '{imp}'"
                )

    assert scanned_files > 0, "At least one plugin file must be scanned"


def test_b4_boundary_plugins_no_direct_orm_models():
    """B4: plugins/ must NOT directly import Tortoise models (must use DAO/services layer)."""
    forbidden_prefixes = (
        "zxtg.models",
        "tortoise.models",
    )

    plugins_dir = PROJECT_ROOT / "plugins"
    for py_file in plugins_dir.rglob("*.py"):
        imports = get_all_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_prefixes:
                assert not (imp == forbidden or imp.startswith(f"{forbidden}.")), (
                    f"Boundary B4 VIOLATION in {py_file}: direct ORM model import '{imp}'"
                )


def test_b2_boundary_platform_no_business_semantics():
    """B2: core/platform/tg/ must NOT contain business semantic words (Design §2.2)."""
    forbidden_words = (
        "签到",
        "金币",
        "checkin",
        "sign_in",
        "coin",
        "gold",
        "impression",
        "好感度",
    )

    tg_platform_dir = PROJECT_ROOT / "src" / "zxtg" / "core" / "platform" / "tg"
    assert tg_platform_dir.exists(), f"Directory {tg_platform_dir} must exist"

    import re

    scanned_files = 0
    for py_file in tg_platform_dir.rglob("*.py"):
        scanned_files += 1
        content = py_file.read_text(encoding="utf-8").lower()
        for word in forbidden_words:
            if re.match(r"^[a-z_]+$", word):
                matched = bool(re.search(rf"\b{word}\b", content))
            else:
                matched = word in content
            assert not matched, (
                f"Boundary B2 VIOLATION in {py_file}: forbidden business word '{word}' found"
            )

    assert scanned_files > 0, "At least one tg platform file must be scanned"


def test_httpx_restricted_to_platform_layer():
    """httpx must ONLY be imported within core/platform/."""
    src_dir = PROJECT_ROOT / "src" / "zxtg"
    platform_dir = src_dir / "core" / "platform"

    for py_file in src_dir.rglob("*.py"):
        if py_file.is_relative_to(platform_dir):
            continue
        imports = get_all_imports(py_file)
        for imp in imports:
            assert imp != "httpx" and not imp.startswith("httpx."), (
                f"httpx import VIOLATION in {py_file}: httpx is only allowed in platform layer"
            )


def test_b5_boundary_plugins_no_raw_sql_drivers():
    """FR-DATA-04: plugins/ must NOT import raw database drivers directly."""
    forbidden_prefixes = (
        "sqlite3",
        "aiosqlite",
        "tortoise.transactions",
        "tortoise.backends",
        "tortoise.connection",
    )

    plugins_dir = PROJECT_ROOT / "plugins"
    for py_file in plugins_dir.rglob("*.py"):
        imports = get_all_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_prefixes:
                assert not (imp == forbidden or imp.startswith(f"{forbidden}.")), (
                    f"FR-DATA-04 VIOLATION in {py_file}: raw SQL driver import '{imp}'"
                )

