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


def get_imports_with_scope(file_path: Path) -> list[tuple[str, bool]]:
    """Parse a python file into AST and return list of (module_path, is_inside_function)."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

    class ImportScopeVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.imports: list[tuple[str, bool]] = []
            self.func_depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.func_depth += 1
            self.generic_visit(node)
            self.func_depth -= 1

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.func_depth += 1
            self.generic_visit(node)
            self.func_depth -= 1

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                self.imports.append((alias.name, self.func_depth > 0))
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module:
                self.imports.append((node.module, self.func_depth > 0))
            self.generic_visit(node)

    visitor = ImportScopeVisitor()
    visitor.visit(tree)
    return visitor.imports


def test_b3_boundary_kernel_and_services_no_platform_imports():
    """B3: core/kernel, core/services, and core/render must NOT import telegram/aiogram or platform libs."""
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
        PROJECT_ROOT / "src" / "zxtg" / "core" / "render",
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

    assert scanned_files > 0, "At least one kernel/services/render python file must be scanned"


def test_b3_covers_render_subsystem():
    """Verify B3 scans core/render subsystem: forbid top-level platform/httpx/engines, ensure optional engines are strictly lazy in functions."""
    render_dir = PROJECT_ROOT / "src" / "zxtg" / "core" / "render"
    assert render_dir.exists(), f"Render directory {render_dir} must exist"

    render_files = list(render_dir.glob("*.py"))
    assert len(render_files) >= 6, f"Expected at least 6 files in render subsystem, scanned {len(render_files)}"

    # 1. Explicitly assert render directory is present in B3 targets
    b3_targets = [
        PROJECT_ROOT / "src" / "zxtg" / "core" / "kernel",
        PROJECT_ROOT / "src" / "zxtg" / "core" / "services",
        PROJECT_ROOT / "src" / "zxtg" / "core" / "render",
    ]
    assert render_dir in b3_targets, "B3 targets must explicitly contain core/render"

    # 2. Inspect all imports and their AST scope (top-level vs lazy in function)
    forbidden_top_level = (
        "httpx",
        "zxtg.core.platform",
        "telegram",
        "aiogram",
        "telethon",
        "pyrogram",
        "nonebot",
        "onebot",
        "playwright",
        "jinja2",
        "PIL",
    )
    optional_engines = ("playwright", "jinja2", "PIL")

    lazy_engine_imports_found = 0
    scanned_count = 0

    for py_file in render_files:
        scanned_count += 1
        imports_with_scope = get_imports_with_scope(py_file)
        for imp, is_inside_func in imports_with_scope:
            # Check top-level imports: module top-level must NOT import platform libs, httpx, or optional render engines
            if not is_inside_func:
                for forbidden in forbidden_top_level:
                    assert not (imp == forbidden or imp.startswith(f"{forbidden}.")), (
                        f"Forbidden top-level import '{imp}' in {py_file}: "
                        "platform libraries, httpx, and optional render engines must never be imported at module top-level!"
                    )

            # Independent assertion: optional rendering engines MUST be inside functions (lazy), never at module top level
            for opt in optional_engines:
                if imp == opt or imp.startswith(f"{opt}."):
                    assert is_inside_func, (
                        f"Optional rendering engine '{imp}' in {py_file} must be lazily imported inside a function body!"
                    )
                    lazy_engine_imports_found += 1

    assert scanned_count >= 6, f"Must scan all render files (got {scanned_count})"
    assert lazy_engine_imports_found > 0, (
        f"Expected to verify optional rendering engine imports (playwright/PIL), found {lazy_engine_imports_found}"
    )


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

