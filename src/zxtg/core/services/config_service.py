import json
import logging
import re
from typing import Any

from zxtg.core.kernel.manifest import CONFIG_KEY_REGEX, ConfigSpec

logger = logging.getLogger("zxtg.services.config")

TYPE_MAP = {
    "int": "integer",
    "float": "number",
    "str": "string",
    "bool": "boolean",
    "list": "array",
    "json": "object",
    "dict": "object",
}


class ConfigService:
    """Three-tier configuration manager: default (manifest) -> global -> group (FR-CFG-01~08)."""

    def __init__(self) -> None:
        # specs: (plugin_key, config_key) -> ConfigSpec
        self._specs: dict[tuple[str, str], ConfigSpec] = {}
        # key_to_specs: config_key -> list[ConfigSpec]
        self._key_to_specs: dict[str, list[ConfigSpec]] = {}
        # global_configs: config_key -> value
        self._global_configs: dict[str, Any] = {}
        # group_configs: (group_id, config_key) -> value
        self._group_configs: dict[tuple[str, str], Any] = {}

    def register_spec(self, plugin_key: str, spec: ConfigSpec) -> None:
        """Register a ConfigSpec declared by a plugin."""
        self._specs[(plugin_key, spec.key)] = spec
        if spec.key not in self._key_to_specs:
            self._key_to_specs[spec.key] = []
        if spec not in self._key_to_specs[spec.key]:
            self._key_to_specs[spec.key].append(spec)

    def get_spec(self, key: str, plugin_key: str | None = None) -> ConfigSpec | None:
        """Retrieve the ConfigSpec for a key, optionally filtered by plugin_key."""
        if plugin_key:
            return self._specs.get((plugin_key, key))
        specs = self._key_to_specs.get(key, [])
        return specs[0] if specs else None

    def validate_value(self, spec: ConfigSpec, value: Any) -> Any:
        """Validate value against type, range, choices, and return converted/valid value (FR-CFG-07)."""
        # 1. Type validation
        expected_type = spec.type.lower()
        if expected_type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                if isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        raise ValueError(f"Config '{spec.key}' expected int, got invalid string: {value!r}")
                else:
                    raise ValueError(f"Config '{spec.key}' expected int, got {type(value).__name__}")
        elif expected_type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                if isinstance(value, str):
                    try:
                        value = float(value)
                    except ValueError:
                        raise ValueError(f"Config '{spec.key}' expected float, got invalid string: {value!r}")
                else:
                    raise ValueError(f"Config '{spec.key}' expected float, got {type(value).__name__}")
            value = float(value)
        elif expected_type == "str":
            if not isinstance(value, str):
                raise ValueError(f"Config '{spec.key}' expected str, got {type(value).__name__}")
        elif expected_type == "bool":
            if not isinstance(value, bool):
                if isinstance(value, str) and value.lower() in ("true", "1", "yes"):
                    value = True
                elif isinstance(value, str) and value.lower() in ("false", "0", "no"):
                    value = False
                else:
                    raise ValueError(f"Config '{spec.key}' expected bool, got {type(value).__name__}")
        elif expected_type == "list":
            if not isinstance(value, (list, tuple)):
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            value = parsed
                        else:
                            raise ValueError
                    except Exception:
                        raise ValueError(f"Config '{spec.key}' expected list, got unparseable string: {value!r}")
                else:
                    raise ValueError(f"Config '{spec.key}' expected list, got {type(value).__name__}")
        elif expected_type in ("json", "dict"):
            if not isinstance(value, (dict, list)):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except Exception:
                        raise ValueError(f"Config '{spec.key}' expected JSON object, got invalid string: {value!r}")
                else:
                    raise ValueError(f"Config '{spec.key}' expected JSON object/dict, got {type(value).__name__}")

        # 2. Min / Max range validation
        if spec.min_value is not None:
            if isinstance(value, (int, float)) and value < spec.min_value:
                raise ValueError(
                    f"Config '{spec.key}' value {value} is less than min_value {spec.min_value}"
                )
        if spec.max_value is not None:
            if isinstance(value, (int, float)) and value > spec.max_value:
                raise ValueError(
                    f"Config '{spec.key}' value {value} is greater than max_value {spec.max_value}"
                )

        # 3. Choices validation
        if spec.choices is not None:
            if value not in spec.choices:
                raise ValueError(
                    f"Config '{spec.key}' value {value!r} is not in allowed choices {spec.choices}"
                )

        return value

    def set_global(self, key: str, value: Any, plugin_key: str | None = None) -> None:
        """Set a global-level configuration value with validation."""
        if not CONFIG_KEY_REGEX.match(key):
            raise ValueError(f"Config key {key!r} violates regex ^[A-Z][A-Z0-9_]{{1,63}}$")
        spec = self.get_spec(key, plugin_key)
        if spec:
            value = self.validate_value(spec, value)
        self._global_configs[key] = value

    async def save_global(self, key: str, value: Any, plugin_key: str | None = None) -> None:
        """Set and persist a global-level configuration value to database (FR-CFG-01, Design §5.6)."""
        if not CONFIG_KEY_REGEX.match(key):
            raise ValueError(f"Config key {key!r} violates regex ^[A-Z][A-Z0-9_]{{1,63}}$")
        spec = self.get_spec(key, plugin_key)
        if spec:
            value = self.validate_value(spec, value)
            if plugin_key is None:
                for (p, k), s in self._specs.items():
                    if k == key and s == spec:
                        plugin_key = p
                        break

        value_json = json.dumps(value, ensure_ascii=False)
        scope = spec.scope if spec and spec.scope else "global"

        from tortoise import Tortoise

        if not Tortoise._inited:
            raise RuntimeError("Database not initialized, cannot persist global config")

        from zxtg.models.config import CoreConfig

        record = await CoreConfig.filter(key=key).first()
        if record:
            record.value_json = value_json
            if plugin_key:
                record.plugin_key = plugin_key
            record.scope = scope
            await record.save(update_fields=["value_json", "plugin_key", "scope", "updated_at"])
        else:
            await CoreConfig.create(
                key=key,
                value_json=value_json,
                plugin_key=plugin_key,
                scope=scope,
            )

        self._global_configs[key] = value

    async def load_global(self, key: str | None = None) -> Any:
        """Load persisted global configs from DB into memory (FR-CFG-01)."""
        from tortoise import Tortoise

        if not Tortoise._inited:
            raise RuntimeError("Database not initialized, cannot load global config")

        from zxtg.models.config import CoreConfig

        if key is not None:
            record = await CoreConfig.filter(key=key).first()
            if record:
                val = json.loads(record.value_json)
                self._global_configs[key] = val
                return val
            return None

        records = await CoreConfig.all()
        for record in records:
            self._global_configs[record.key] = json.loads(record.value_json)
        return self._global_configs

    def set_group(self, group_id: str, key: str, value: Any, plugin_key: str | None = None) -> None:
        """Set a group-level configuration value with validation and scope checking."""
        if not CONFIG_KEY_REGEX.match(key):
            raise ValueError(f"Config key {key!r} violates regex ^[A-Z][A-Z0-9_]{{1,63}}$")
        spec = self.get_spec(key, plugin_key)
        if spec:
            if spec.scope == "global":
                raise ValueError(
                    f"Config '{spec.key}' has scope 'global' and cannot be set at group level"
                )
            value = self.validate_value(spec, value)
        self._group_configs[(str(group_id), key)] = value

    def get(self, key: str, group_id: str | None = None, plugin_key: str | None = None) -> Any:
        """Three-tier configuration resolution: Group -> Global -> Default (FR-CFG-01)."""
        # 1. Group level
        if group_id is not None:
            group_key = (str(group_id), key)
            if group_key in self._group_configs:
                return self._group_configs[group_key]

        # 2. Global level
        if key in self._global_configs:
            return self._global_configs[key]

        # 3. Default from Spec
        spec = self.get_spec(key, plugin_key)
        if spec is not None:
            return spec.default

        return None

    def get_plugin_effective_configs(
        self, plugin_key: str, group_id: str | None = None
    ) -> dict[str, Any]:
        """Resolve all effective configs for a given plugin."""
        result = {}
        for (p_key, c_key), spec in self._specs.items():
            if p_key == plugin_key:
                result[c_key] = self.get(c_key, group_id=group_id, plugin_key=plugin_key)
        return result

    def export_json_schema(self, plugin_key: str | None = None) -> dict[str, Any]:
        """Export configuration items as standard JSON Schema (FR-CFG-05)."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        specs_to_export = [
            spec for (p_key, _), spec in self._specs.items()
            if plugin_key is None or p_key == plugin_key
        ]

        for spec in specs_to_export:
            schema_type = TYPE_MAP.get(spec.type.lower(), "string")
            prop_def: dict[str, Any] = {
                "type": schema_type,
                "description": spec.help,
                "default": spec.default,
            }
            if spec.min_value is not None:
                prop_def["minimum"] = spec.min_value
            if spec.max_value is not None:
                prop_def["maximum"] = spec.max_value
            if spec.choices is not None:
                prop_def["enum"] = list(spec.choices)
            if spec.scope:
                prop_def["scope"] = spec.scope

            properties[spec.key] = prop_def
            required.append(spec.key)

        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": f"PluginConfigSchema_{plugin_key}" if plugin_key else "PluginConfigSchema",
            "properties": properties,
            "required": required,
        }

    def clear(self) -> None:
        """Reset service state for testing."""
        self._specs.clear()
        self._key_to_specs.clear()
        self._global_configs.clear()
        self._group_configs.clear()


config_service = ConfigService()
