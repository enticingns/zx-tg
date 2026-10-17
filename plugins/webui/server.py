import asyncio
import html
import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from plugins.webui.auth import (
    TokenExpiredError,
    TokenInvalidError,
    auth_manager,
)
from zxtg.core.kernel.registry import registry
from zxtg.core.services.config_service import config_service
from zxtg.core.services.group_service import group_service

logger = logging.getLogger("zxtg.webui")


class LoginRequest(BaseModel):
    username: str
    password: str


class ConfigUpdateRequest(BaseModel):
    value: Any
    group_id: str | None = None


class PluginToggleRequest(BaseModel):
    status: bool | None = None


class GroupLevelRequest(BaseModel):
    level: int


class GroupStatusRequest(BaseModel):
    status: bool


def create_app() -> FastAPI:
    """Create and configure FastAPI WebUI application (FR-WEB-01~07)."""
    app = FastAPI(title="ZX-TG WebUI Management Console", docs_url=None, redoc_url=None)

    async def get_current_user(authorization: str | None = Header(None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authentication header",
            )
        token = authorization.split(" ", 1)[1]
        try:
            payload = auth_manager.verify_token(token)
            return str(payload.get("sub", "admin"))
        except TokenExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired",
            )
        except TokenInvalidError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )

    @app.post("/api/login")
    async def login(req: LoginRequest) -> dict[str, Any]:
        """Authenticate and issue JWT token with TTL (FR-WEB-03, NFR-09)."""
        expected_user = config_service.get("WEBUI_USERNAME") or "admin"
        expected_pwd = config_service.get("WEBUI_PASSWORD") or "admin"
        ttl = int(config_service.get("WEBUI_TOKEN_TTL") or 3600)

        if req.username == expected_user and req.password == expected_pwd:
            auth_manager.clear_failures(req.username)
            token = auth_manager.create_token(req.username, ttl_seconds=ttl)
            return {
                "token": token,
                "token_type": "bearer",
                "expires_in": ttl,
            }

        cnt = auth_manager.record_failure(req.username)
        logger.warning("WebUI failed login attempt for user '%s' (failure count: %d)", req.username, cnt)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    @app.get("/api/status")
    async def get_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
        """Runtime system health and status check (FR-WEB-04)."""
        return {
            "status": "online",
            "plugins_count": len(registry._plugins),
            "user": user,
        }

    @app.get("/api/plugins")
    async def list_plugins(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
        """List registered plugins and their enabled status (FR-WEB-04)."""
        res = []
        for key, p in registry._plugins.items():
            enabled = await group_service.get_global_plugin_switch(key)
            res.append({
                "key": p.key,
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "menu_type": p.menu_type,
                "enabled": enabled,
            })
        return res

    @app.post("/api/plugins/{plugin_key}/toggle")
    async def toggle_plugin(
        plugin_key: str,
        req: PluginToggleRequest | None = None,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Toggle global plugin active status (FR-WEB-04)."""
        p = registry.get_plugin(plugin_key)
        if not p:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_key}' not found")

        current = await group_service.get_global_plugin_switch(plugin_key)
        new_status = req.status if (req and req.status is not None) else not current
        await group_service.set_global_plugin_switch(plugin_key, new_status)
        return {"plugin_key": plugin_key, "status": new_status}

    @app.get("/api/configs")
    async def list_configs(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
        """List configuration items (FR-WEB-04)."""
        res = []
        for (p_key, c_key), spec in config_service._specs.items():
            val = config_service.get(c_key, plugin_key=p_key)
            res.append({
                "plugin_key": p_key,
                "key": c_key,
                "type": spec.type,
                "value": val,
                "default": spec.default,
                "help": spec.help,
                "scope": spec.scope,
            })
        return res

    @app.put("/api/configs/{key}")
    async def update_config(
        key: str,
        req: ConfigUpdateRequest,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Update and persist configuration value with validation (FR-WEB-04)."""
        try:
            if req.group_id:
                await config_service.save_group(req.group_id, key, req.value)
            else:
                await config_service.save_global(key, req.value)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {"key": key, "value": req.value, "group_id": req.group_id, "saved": True}

    @app.get("/api/schema")
    async def get_config_schema(
        plugin_key: str | None = None,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Export JSON Schema for configuration form auto-rendering (FR-WEB-05)."""
        return config_service.export_json_schema(plugin_key)

    @app.get("/api/form", response_class=HTMLResponse)
    async def get_rendered_form(
        plugin_key: str | None = None,
        user: str = Depends(get_current_user),
    ) -> str:
        """Render configuration HTML form dynamically from JSON Schema (FR-WEB-05)."""
        schema = config_service.export_json_schema(plugin_key)
        props = schema.get("properties", {})
        form_elements = [
            f"<div class='schema-form'><h3>{html.escape(schema.get('title', 'Config Form'))}</h3>",
            "<form id='config-form' method='POST' action='/api/configs'>",
        ]

        for k, prop in props.items():
            prop_type = prop.get("type", "string")
            desc = html.escape(prop.get("description", ""))
            curr_val = config_service.get(k)
            enum_choices = prop.get("enum")

            form_elements.append(f"<div class='form-group' style='margin-bottom: 12px;'>")
            form_elements.append(f"<label for='field_{k}'><strong>{html.escape(k)}</strong> ({prop_type})</label><br>")
            if desc:
                form_elements.append(f"<small style='color: #64748b;'>{desc}</small><br>")

            if enum_choices:
                form_elements.append(f"<select id='field_{k}' name='{k}'>")
                for ch in enum_choices:
                    sel = "selected" if str(ch) == str(curr_val) else ""
                    form_elements.append(f"<option value='{html.escape(str(ch))}' {sel}>{html.escape(str(ch))}</option>")
                form_elements.append("</select>")
            elif prop_type in ("integer", "number"):
                min_attr = f"min='{prop['minimum']}'" if "minimum" in prop else ""
                max_attr = f"max='{prop['maximum']}'" if "maximum" in prop else ""
                form_elements.append(f"<input type='number' id='field_{k}' name='{k}' value='{curr_val}' {min_attr} {max_attr} />")
            elif prop_type == "boolean":
                checked = "checked" if curr_val else ""
                form_elements.append(f"<input type='checkbox' id='field_{k}' name='{k}' {checked} />")
            else:
                val_str = html.escape(str(curr_val if curr_val is not None else ""))
                form_elements.append(f"<input type='text' id='field_{k}' name='{k}' value='{val_str}' style='width: 300px;' />")

            form_elements.append("</div>")

        form_elements.append("<button type='submit'>Save Configuration</button></form></div>")
        return "\n".join(form_elements)

    @app.get("/api/groups")
    async def list_groups(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
        """List groups for management (FR-WEB-04)."""
        return await group_service.list_groups()

    @app.put("/api/groups/{group_id}/level")
    async def update_group_level(
        group_id: str,
        req: GroupLevelRequest,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Update group authorization level (FR-WEB-04)."""
        await group_service.set_group_level(group_id, req.level)
        return {"group_id": group_id, "level": req.level}

    @app.put("/api/groups/{group_id}/status")
    async def update_group_status(
        group_id: str,
        req: GroupStatusRequest,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Update group active status (FR-WEB-04)."""
        await group_service.set_group_status(group_id, req.status)
        return {"group_id": group_id, "status": req.status}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        """Lightweight WebUI landing page."""
        return """<!DOCTYPE html>
<html>
<head><title>ZX-TG WebUI</title></head>
<body>
  <h1>ZX-TG WebUI Management Console</h1>
  <p>Status: Ready. Use authenticated API endpoints to manage plugins, configs, and groups.</p>
</body>
</html>"""

    return app


class WebUIServer:
    """Asyncio background server manager with zero leftover tasks on stop (FR-WEB-02, FR-WEB-07)."""

    def __init__(self, app: FastAPI | None = None) -> None:
        self.app = app or create_app()
        self.server: uvicorn.Server | None = None
        self.task: asyncio.Task | None = None

    async def start(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        if self.task and not self.task.done():
            return

        if host == "0.0.0.0":
            logger.warning("WebUI host is set to 0.0.0.0 (public access)! Ensure firewall/proxy security (FR-WEB-02).")

        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_config=None,
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.task = asyncio.create_task(self.server.serve())

        # Wait briefly for startup
        for _ in range(50):
            if self.server.started:
                break
            await asyncio.sleep(0.02)

    async def stop(self) -> None:
        """Stop uvicorn server and cancel/await task cleanly (FR-WEB-07)."""
        if self.server:
            self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                self.task.cancel()
                try:
                    await self.task
                except (asyncio.CancelledError, Exception):
                    pass
            self.task = None
        self.server = None


webui_server = WebUIServer()
