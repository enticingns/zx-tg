import asyncio
import logging
from pathlib import Path
import sys
import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import plugins.webui.plugin as webui_plugin
from plugins.webui.auth import auth_manager
from plugins.webui.server import WebUIServer, create_app, webui_server
from zxtg.core.kernel.registry import registry
from zxtg.core.services.config_service import config_service
from zxtg.core.services.db import close_db, init_db
from zxtg.core.services.group_service import group_service


@pytest.fixture(autouse=True)
async def setup_webui_test():
    await init_db(db_path=":memory:", generate_schemas=True)
    registry.clear()
    await registry.startup()
    config_service.set_global("WEBUI_USERNAME", "admin")
    config_service.set_global("WEBUI_PASSWORD", "admin123")
    config_service.set_global("WEBUI_TOKEN_TTL", 3600)
    config_service.set_global("WEBUI_HOST", "127.0.0.1")
    config_service.set_global("WEBUI_PORT", 8080)
    auth_manager.clear_failures()
    yield
    await webui_server.stop()
    await close_db()


def test_webui_default_host_is_loopback(caplog):
    """7. test_webui_default_host_is_loopback: default configuration binds to 127.0.0.1; 0.0.0.0 warns (FR-WEB-02)."""
    # 7A. Verify manifest default is loopback
    host_spec = next((cfg for cfg in webui_plugin.manifest.configs if cfg.key == "WEBUI_HOST"), None)
    assert host_spec is not None
    assert host_spec.default == "127.0.0.1", "WebUI default host must strictly be 127.0.0.1"

    # 7B. Starting with 0.0.0.0 logs warning
    srv = WebUIServer(create_app())
    with caplog.at_level(logging.WARNING, logger="zxtg.webui"):
        asyncio.run(srv.start(host="0.0.0.0", port=18088))
        assert any("0.0.0.0" in r.message for r in caplog.records), "Binding to 0.0.0.0 must emit security warning log"
        asyncio.run(srv.stop())


@pytest.mark.asyncio
async def test_webui_token_expiry_rejects_expired():
    """8. test_webui_token_expiry_rejects_expired: expired tokens are strictly rejected with 401 (FR-WEB-03)."""
    app = create_app()
    # Create token already expired in the past
    expired_token = auth_manager.create_token("admin", ttl_seconds=-10)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401, "Expired token must be rejected with 401"
        data = resp.json()
        assert "expired" in data.get("detail", "").lower()


@pytest.mark.asyncio
async def test_webui_disabled_leaves_no_tasks():
    """9. test_webui_disabled_leaves_no_tasks: closing WebUI leaves zero lingering tasks or sockets (FR-WEB-07)."""
    srv = WebUIServer(create_app())
    # 1. Start server
    await srv.start(host="127.0.0.1", port=18090)
    assert srv.task is not None
    assert not srv.task.done()

    # 2. Stop server
    await srv.stop()
    assert srv.task is None
    assert srv.server is None

    # Verify no running server tasks left in asyncio event loop
    all_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    webui_tasks = [t for t in all_tasks if "serve" in str(t) or "uvicorn" in str(t)]
    assert len(webui_tasks) == 0, f"No leftover uvicorn tasks allowed after stop, found: {webui_tasks}"


@pytest.mark.asyncio
async def test_webui_plugin_toggle_and_config():
    """10. test_webui_plugin_toggle_and_config: toggles plugin switch and updates persisted config (FR-WEB-04)."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login
        login_resp = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Check and toggle plugin switch
        resp_toggle = await client.post("/api/plugins/sign_in/toggle", json={"status": False}, headers=headers)
        assert resp_toggle.status_code == 200
        assert resp_toggle.json()["status"] is False

        # Read back via API
        resp_plugins = await client.get("/api/plugins", headers=headers)
        assert resp_plugins.status_code == 200
        sign_in_item = next(p for p in resp_plugins.json() if p["key"] == "sign_in")
        assert sign_in_item["enabled"] is False

        # Toggle back to True
        resp_toggle2 = await client.post("/api/plugins/sign_in/toggle", json={"status": True}, headers=headers)
        assert resp_toggle2.json()["status"] is True

        # 3. Update config and verify persistence (FR-CFG-01, FR-WEB-04)
        resp_cfg = await client.put(
            "/api/configs/SIGN_GOLD_MIN",
            json={"value": 66},
            headers=headers,
        )
        assert resp_cfg.status_code == 200
        assert resp_cfg.json()["saved"] is True

        # Verify persisted value read through service
        val = config_service.get("SIGN_GOLD_MIN")
        assert val == 66

        # Verify DB persistence directly via load_global
        db_val = await config_service.load_global("SIGN_GOLD_MIN")
        assert db_val == 66, "Config update must be persisted to database, not just memory"


@pytest.mark.asyncio
async def test_webui_requires_auth():
    """11. test_webui_requires_auth: unauthenticated requests receive 401/403 and return NO data (FR-WEB-03)."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Endpoints that must be protected
        protected_endpoints = [
            ("GET", "/api/status"),
            ("GET", "/api/plugins"),
            ("POST", "/api/plugins/sign_in/toggle"),
            ("GET", "/api/configs"),
            ("PUT", "/api/configs/SIGN_GOLD_MIN"),
            ("GET", "/api/schema"),
            ("GET", "/api/groups"),
            ("GET", "/api/form"),
        ]

        for method, endpoint in protected_endpoints:
            if method == "GET":
                resp = await client.get(endpoint)
            elif method == "POST":
                resp = await client.post(endpoint, json={})
            elif method == "PUT":
                resp = await client.put(endpoint, json={"value": 1})

            assert resp.status_code in (401, 403), f"Endpoint {endpoint} must require authentication"
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            # Must not return data payloads
            assert "plugins" not in str(body).lower() or "detail" in str(body).lower()
            assert "token" not in str(body).lower()


@pytest.mark.asyncio
async def test_webui_json_schema_form_rendering():
    """FR-WEB-05: JSON Schema export and automatic HTML form generation."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = auth_manager.create_token("admin", 3600)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. JSON Schema endpoint returns valid schema
        resp_schema = await client.get("/api/schema", headers=headers)
        assert resp_schema.status_code == 200
        schema = resp_schema.json()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "properties" in schema

        # 2. Form endpoint returns auto-rendered form inputs matching schema
        resp_form = await client.get("/api/form", headers=headers)
        assert resp_form.status_code == 200
        content = resp_form.text
        assert "<form" in content
        assert "Save Configuration" in content
        # Check that input elements are generated
        assert "<input" in content


@pytest.mark.asyncio
async def test_webui_login_failure_rate_tracking():
    """Security: Failed logins increment failure counter and reject invalid credentials."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert auth_manager.get_failure_count("bad_user") == 0

        # Attempt 1
        resp1 = await client.post("/api/login", json={"username": "bad_user", "password": "wrong"})
        assert resp1.status_code == 401
        assert auth_manager.get_failure_count("bad_user") == 1

        # Attempt 2
        resp2 = await client.post("/api/login", json={"username": "bad_user", "password": "wrong2"})
        assert resp2.status_code == 401
        assert auth_manager.get_failure_count("bad_user") == 2
