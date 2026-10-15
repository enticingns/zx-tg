from collections.abc import Callable, Coroutine
import importlib.util
import logging
from pathlib import Path
import sys
from typing import Any

from tortoise import Tortoise

from zxtg.core.kernel.commands import (
    command_registry,
    compute_effective_slash,
    validate_slash_syntax,
)
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import (
    BotPerm,
    Cmd,
    ConfigSpec,
    EventSpec,
    Example,
    LimitSpec,
    Param,
    PluginManifest,
    TaskSpec,
    matches_semver_range,
    parse_semver,
    validate_callback_data,
)
from zxtg.core.services.config_service import config_service
from zxtg.core.services.limit_service import limit_service
from zxtg.models.plugin_info import PluginInfo

logger = logging.getLogger("zxtg.kernel.registry")

CORE_VERSION = "1.0.0"

HandlerFunc = Callable[..., Coroutine[Any, Any, Any]]


class PluginRegistry:
    """Plugin registry managing discover -> validate -> resolve -> register (FR-PLG-01~09)."""

    def __init__(self, core_version: str = CORE_VERSION) -> None:
        self.core_version = core_version
        self._plugins: dict[str, PluginManifest] = {}
        self._handlers: dict[str, HandlerFunc] = {}
        self._discovered_modules: dict[str, Any] = {}

    def clear(self) -> None:
        """Reset registry state for clean testing."""
        self._plugins.clear()
        self._handlers.clear()
        self._discovered_modules.clear()
        command_registry.clear()
        config_service.clear()
        limit_service.clear()

    def discover(self, search_paths: list[str | Path] | None = None) -> list[PluginManifest]:
        """Scan directories for plugins/*/plugin.py and plugins_ext/*/plugin.py (FR-PLG-01, FR-PLG-05)."""
        paths = search_paths or ["plugins", "plugins_ext"]
        discovered: list[PluginManifest] = []

        for p in paths:
            root_dir = Path(p)
            if not root_dir.exists() or not root_dir.is_dir():
                continue

            for item in sorted(root_dir.iterdir()):
                if not item.is_dir():
                    continue
                if item.name.startswith((".", "_")):
                    continue

                plugin_file = item / "plugin.py"
                if not plugin_file.exists():
                    logger.warning("Plugin directory '%s' missing 'plugin.py', skipping", item)
                    continue

                module_name = f"zxtg_discovered_{item.name}"
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                if spec is None or spec.loader is None:
                    logger.warning("Failed to load spec for '%s'", plugin_file)
                    continue

                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    logger.error("Error executing plugin module '%s': %s", plugin_file, e)
                    raise

                manifest = getattr(mod, "manifest", None)
                if manifest is None or not isinstance(manifest, PluginManifest):
                    logger.warning("Module '%s' does not define a valid PluginManifest 'manifest'", plugin_file)
                    continue

                self._discovered_modules[manifest.key] = mod
                discovered.append(manifest)

        return discovered

    def validate(self, manifests: list[PluginManifest]) -> None:
        """Validate manifests for key conflicts, command/pattern conflicts, cycle deps, and core version (FR-PLG-03~06)."""
        seen_keys: dict[str, PluginManifest] = {}
        seen_cmd_keys: dict[str, tuple[str, str]] = {}      # cmd_key -> (plugin_key, cmd_key)
        seen_slashes: dict[str, tuple[str, str]] = {}       # slash -> (plugin_key, cmd_key)
        seen_patterns: dict[str, tuple[str, str]] = {}      # pattern -> (plugin_key, cmd_key)
        all_manifest_keys = {m.key for m in manifests}

        total_slash_count = 0

        for manifest in manifests:
            # 1. Plugin Key uniqueness
            if manifest.key in seen_keys:
                conflicting = seen_keys[manifest.key]
                raise ValueError(
                    f"Plugin key conflict: '{manifest.key}' defined by both "
                    f"'{conflicting.name}' and '{manifest.name}'"
                )
            seen_keys[manifest.key] = manifest

            # 2. requires_core SemVer range check (FR-PLG-06)
            if not matches_semver_range(self.core_version, manifest.requires_core):
                raise ValueError(
                    f"requires_core mismatch: plugin '{manifest.key}' requires core '{manifest.requires_core}', "
                    f"but current core version is '{self.core_version}'"
                )

            # 3. requires missing check (FR-PLG-04)
            for req in manifest.requires:
                if req not in all_manifest_keys:
                    raise ValueError(
                        f"Missing dependency: plugin '{manifest.key}' requires '{req}', but it was not found"
                    )

            # 4. callback_data <= 64 bytes check (FR-TG-11)
            for cb in manifest.callbacks:
                validate_callback_data(cb)

            # 5. Config keys format & callable prohibition (FR-CFG-02, FR-CFG-04)
            cfg_keys: set[str] = set()
            for cfg in manifest.configs:
                if cfg.key in cfg_keys:
                    raise ValueError(
                        f"Duplicate config key '{cfg.key}' in plugin '{manifest.key}'"
                    )
                cfg_keys.add(cfg.key)

            # 6. Commands conflicts check
            for cmd in manifest.cmds:
                cmd_k = cmd.key.lower()
                if cmd_k in seen_cmd_keys:
                    prev_p, prev_c = seen_cmd_keys[cmd_k]
                    raise ValueError(
                        f"Command key conflict: '{cmd.key}' in plugin '{manifest.key}' "
                        f"conflicts with command '{prev_c}' in plugin '{prev_p}'"
                    )
                seen_cmd_keys[cmd_k] = (manifest.key, cmd.key)

                # Slash conflict check
                effective_slash = compute_effective_slash(manifest.key, cmd)
                validate_slash_syntax(effective_slash)
                total_slash_count += 1
                if effective_slash in seen_slashes:
                    prev_p, prev_c = seen_slashes[effective_slash]
                    raise ValueError(
                        f"Command slash conflict: '/{effective_slash}' in plugin '{manifest.key}' "
                        f"conflicts with command '{prev_c}' in plugin '{prev_p}'"
                    )
                seen_slashes[effective_slash] = (manifest.key, cmd.key)

                # Pattern conflict and prefix check (FR-CMD-09)
                if cmd.pattern:
                    pat = cmd.pattern.lower()
                    if pat in seen_patterns:
                        prev_p, prev_c = seen_patterns[pat]
                        raise ValueError(
                            f"Command pattern conflict: '{cmd.pattern}' in plugin '{manifest.key}' "
                            f"conflicts with command '{prev_c}' in plugin '{prev_p}'"
                        )
                    # Check prefix relation with existing patterns
                    for existing_pat, (prev_p, prev_c) in seen_patterns.items():
                        if pat.startswith(existing_pat) or existing_pat.startswith(pat):
                            raise ValueError(
                                f"Command pattern prefix conflict between '{cmd.pattern}' (plugin '{manifest.key}') "
                                f"and '{existing_pat}' (plugin '{prev_p}')"
                            )
                    seen_patterns[pat] = (manifest.key, cmd.key)

        # 7. Circular dependency check in requires (FR-PLG-04)
        self._check_dependency_cycles(manifests)

        # 8. Warn on >100 slashes (FR-CMD-04)
        if total_slash_count > 100:
            logger.warning(
                "Total slash commands (%d) exceeds Telegram 100 limit, truncation will apply",
                total_slash_count,
            )

        # 9. Warn on bot_permissions (FR-PLG-05)
        for manifest in manifests:
            if manifest.bot_permissions:
                logger.info(
                    "Plugin '%s' requests bot permissions: %s",
                    manifest.key,
                    {str(bp) for bp in manifest.bot_permissions},
                )

    def _check_dependency_cycles(self, manifests: list[PluginManifest]) -> None:
        """Detect circular dependencies in requires."""
        adj: dict[str, list[str]] = {m.key: list(m.requires) for m in manifests}
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        cycle_path: list[str] = []

        def dfs(node: str) -> bool:
            visited[node] = 1
            cycle_path.append(node)
            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    cycle_path.append(neighbor)
                    return True
                if visited.get(neighbor) == 0:
                    if dfs(neighbor):
                        return True
            cycle_path.pop()
            visited[node] = 2
            return False

        for k in adj:
            visited[k] = 0

        for k in adj:
            if visited[k] == 0:
                if dfs(k):
                    cycle_str = " -> ".join(cycle_path)
                    raise ValueError(f"Circular dependency detected in plugin requires: {cycle_str}")

    def resolve(self, manifests: list[PluginManifest]) -> list[PluginManifest]:
        """Topological sort based on requires and declaration order."""
        manifest_map = {m.key: m for m in manifests}
        in_degree: dict[str, int] = {m.key: 0 for m in manifests}
        dependents: dict[str, list[str]] = {m.key: [] for m in manifests}

        for m in manifests:
            for req in m.requires:
                if req in dependents:
                    dependents[req].append(m.key)
                    in_degree[m.key] += 1

        queue = [m.key for m in manifests if in_degree[m.key] == 0]
        sorted_keys: list[str] = []

        while queue:
            current = queue.pop(0)
            sorted_keys.append(current)
            for dep in dependents.get(current, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        return [manifest_map[k] for k in sorted_keys if k in manifest_map]

    async def register_to_db(self, manifest: PluginManifest) -> None:
        """Upsert plugin into PluginInfo table, preserving status/default_status/load_status (FR-PLG-08)."""
        if not Tortoise._inited:
            return

        existing = await PluginInfo.get_or_none(module=manifest.key)
        if existing:
            # Structural update only; DO NOT overwrite status, default_status, load_status
            existing.name = manifest.name
            existing.version = manifest.version
            existing.author = manifest.author
            existing.level = manifest.level
            existing.admin_level = manifest.admin_level
            existing.menu_type = manifest.menu_type
            existing.plugin_type = manifest.plugin_type
            existing.cost_gold = manifest.cost_gold
            existing.impression = manifest.impression
            existing.parent = manifest.parent
            existing.is_show = manifest.is_show
            existing.ignore_prompt = manifest.ignore_prompt
            existing.ignore_statistics = manifest.ignore_statistics
            await existing.save()
        else:
            await PluginInfo.create(
                module=manifest.key,
                module_path=f"plugins.{manifest.key}",
                name=manifest.name,
                version=manifest.version,
                author=manifest.author,
                status=manifest.default_status,
                default_status=manifest.default_status,
                load_status=True,
                level=manifest.level,
                admin_level=manifest.admin_level,
                limit_superuser=manifest.limit_superuser,
                menu_type=manifest.menu_type,
                plugin_type=manifest.plugin_type,
                cost_gold=manifest.cost_gold,
                impression=manifest.impression,
                parent=manifest.parent,
                is_show=manifest.is_show,
                ignore_prompt=manifest.ignore_prompt,
                ignore_statistics=manifest.ignore_statistics,
            )

    async def register_manifest(
        self,
        manifest: PluginManifest,
        handlers: dict[str, HandlerFunc] | None = None,
    ) -> None:
        """Full registration for a single validated manifest into memory and DB."""
        self._plugins[manifest.key] = manifest

        # Register configs into ConfigService
        for cfg in manifest.configs:
            config_service.register_spec(manifest.key, cfg)

        # Register limits into LimitService
        for lim in manifest.limits:
            limit_service.register_limit(manifest.key, lim)

        # Register commands into CommandRegistry
        command_registry.register_plugin_commands(manifest)

        # Register handlers
        if handlers:
            for cmd_name, handler in handlers.items():
                self.register_handler(cmd_name, handler)
                for cmd in manifest.cmds:
                    if cmd.key.lower() == cmd_name.lower():
                        if cmd.pattern:
                            self.register_handler(cmd.pattern, handler)
                        effective_slash = compute_effective_slash(manifest.key, cmd)
                        self.register_handler(effective_slash, handler)
                        for alias in cmd.aliases:
                            self.register_handler(alias, handler)

        # Upsert into database
        await self.register_to_db(manifest)

    def register(
        self,
        manifest: PluginManifest,
        handlers: dict[str, HandlerFunc] | None = None,
    ) -> None:
        """Synchronous register wrapper (M0 backwards compatibility)."""
        self._plugins[manifest.key] = manifest

        for cfg in manifest.configs:
            config_service.register_spec(manifest.key, cfg)

        for lim in manifest.limits:
            limit_service.register_limit(manifest.key, lim)

        command_registry.register_plugin_commands(manifest)

        if handlers:
            for cmd_name, handler in handlers.items():
                self.register_handler(cmd_name, handler)
                for cmd in manifest.cmds:
                    if cmd.key.lower() == cmd_name.lower():
                        if cmd.pattern:
                            self.register_handler(cmd.pattern, handler)
                        effective_slash = compute_effective_slash(manifest.key, cmd)
                        self.register_handler(effective_slash, handler)
                        for alias in cmd.aliases:
                            self.register_handler(alias, handler)

    def register_handler(self, command_name: str, handler: HandlerFunc) -> None:
        """Bind a command identifier to a handler function."""
        self._handlers[command_name.lower()] = handler

    def get_handler(self, command_name: str) -> HandlerFunc | None:
        """Retrieve handler for a command token."""
        return self._handlers.get(command_name.lower())

    def get_plugin(self, key: str) -> PluginManifest | None:
        """Retrieve registered plugin manifest by key."""
        return self._plugins.get(key)

    def list_plugins(self) -> list[PluginManifest]:
        """List all currently registered manifests."""
        return list(self._plugins.values())

    async def startup(self, search_paths: list[str | Path] | None = None) -> list[PluginManifest]:
        """Orchestrate discover -> validate -> resolve -> register -> recalculate_truncation."""
        manifests = self.discover(search_paths)
        self.validate(manifests)
        resolved = self.resolve(manifests)

        for manifest in resolved:
            mod = self._discovered_modules.get(manifest.key)
            handlers: dict[str, HandlerFunc] = {}
            if mod:
                for cmd in manifest.cmds:
                    handler_name = f"handle_{cmd.key}"
                    func = getattr(mod, handler_name, None)
                    if func and callable(func):
                        handlers[cmd.key] = func
            await self.register_manifest(manifest, handlers)

        command_registry.recalculate_truncation()
        return resolved


registry = PluginRegistry()
