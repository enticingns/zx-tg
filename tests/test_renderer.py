import io
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zxtg.core.context import CallContext, GroupView, SentMessage, UserView
from zxtg.core.event import Actor, ChatRef, Role, UnifiedEvent
from zxtg.core.render.pillow_engine import PillowRenderer
from zxtg.core.render.port import RenderResult
from zxtg.core.render.registry import RenderRegistry, render_registry, render_with_fallback
from zxtg.core.render.text import TextRenderer
from zxtg.core.services.config_service import config_service
from zxtg.core.services.db import close_db, init_db
from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.impression_service import impression_service
from zxtg.core.services.user_service import user_service
import plugins.sign_in.plugin as sign_in_plugin


@pytest.fixture(autouse=True)
async def setup_renderer_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    config_service.clear()
    render_registry.clear_warned()
    yield
    await close_db()


def test_text_renderer_zero_dependency():
    """1. test_text_renderer_zero_dependency: text engine works zero-dependency and outputs Markdown."""
    renderer = TextRenderer()
    avail, guide = renderer.is_available()
    assert avail is True
    assert guide is None
    assert renderer.name == "text"

    import asyncio

    # Test sign_in template
    res = asyncio.run(
        renderer.render(
            "sign_in",
            {"gold_reward": 25, "current_gold": 125, "imp_reward": 1.5, "current_imp": 11.5},
        )
    )
    assert res.engine == "text"
    assert res.content_type == "text/markdown"
    assert res.is_text is True
    assert res.is_image is False
    assert "签到成功" in res.content
    assert "+25" in res.content
    assert "+1.5" in res.content

    # Test sign_rank template
    rank_res = asyncio.run(
        renderer.render(
            "sign_rank",
            {"title": "测试排行榜", "ranking": [{"name": "alice", "impression": 99.0}]},
        )
    )
    assert rank_res.engine == "text"
    assert "测试排行榜" in rank_res.content
    assert "1. alice - 99.0" in rank_res.content


def test_pillow_renderer_produces_image():
    """2. test_pillow_renderer_produces_image: pillow outputs valid PNG bytes with \\x89PNG header."""
    renderer = PillowRenderer()
    avail, guide = renderer.is_available()
    assert avail is True, f"Pillow should be installed in dev environment: {guide}"

    import asyncio

    res = asyncio.run(
        renderer.render(
            "sign_in",
            {
                "gold_reward": 20,
                "current_gold": 220,
                "imp_reward": 2.0,
                "current_imp": 12.0,
                "user_id": "test_user_1",
            },
        )
    )
    assert res.engine == "pillow"
    assert res.content_type == "image/png"
    assert res.is_image is True
    assert res.is_text is False
    assert isinstance(res.content, bytes)
    assert len(res.content) > 100
    assert res.content.startswith(b"\x89PNG\r\n\x1a\n"), "PNG magic header must be present"


@pytest.mark.asyncio
async def test_render_degrades_when_pillow_missing(monkeypatch):
    """3. test_render_degrades_when_pillow_missing: degraded to text when pillow is unavailable with readable guide."""
    reg = RenderRegistry()
    # Mock PillowRenderer to report unavailable
    monkeypatch.setattr(
        reg.get("pillow"),
        "is_available",
        lambda: (False, "图片渲染引擎 Pillow 未安装，已降级为文本；安装方法：pip install zxtg[render]"),
    )

    res = await reg.render("sign_in", {"gold_reward": 15, "current_gold": 115, "imp_reward": 1.0, "current_imp": 6.0}, engine="pillow")

    # Assertions: no exception, degraded to text, engine=='text', readable notice
    assert res.engine == "text", "Engine must truthfully report 'text' after degradation"
    assert res.content_type == "text/markdown"
    assert isinstance(res.content, str)
    assert "签到成功" in res.content
    assert res.notice is not None
    assert "pip install zxtg[render]" in res.notice
    assert "Pillow 未安装" in res.notice


@pytest.mark.asyncio
async def test_render_engine_never_lies(monkeypatch):
    """4. test_render_engine_never_lies: negative control ensures engine truthfully reflects degraded reality."""
    reg = RenderRegistry()
    monkeypatch.setattr(
        reg.get("pillow"),
        "is_available",
        lambda: (False, "Pillow missing"),
    )

    res = await reg.render("sign_in", {"gold_reward": 10}, engine="pillow")

    # Contract: if content is text, engine MUST NOT claim to be pillow!
    assert res.engine == "text", "Degraded output must have engine=='text'"
    assert not (res.engine == "pillow" and isinstance(res.content, str)), "Engine must never lie about its output format"


def test_core_import_without_optional_deps():
    """5. test_core_import_without_optional_deps: core import & commands work when optional deps are unavailable."""
    hidden_modules = {
        "PIL": None,
        "PIL.Image": None,
        "fastapi": None,
        "uvicorn": None,
        "jwt": None,
        "playwright": None,
        "jinja2": None,
    }
    with patch.dict("sys.modules", hidden_modules):
        # Top-level import of core and render modules must not raise ImportError
        import zxtg
        import zxtg.core.context
        import zxtg.core.render.pillow_engine
        import zxtg.core.render.text
        import zxtg.core.render.registry

        assert zxtg.__name__ == "zxtg"
        # PillowRenderer.is_available safely returns False instead of crashing
        p_renderer = zxtg.core.render.pillow_engine.PillowRenderer()
        avail, guide = p_renderer.is_available()
        assert avail is False
        assert guide is not None
        assert "pip install zxtg[render]" in guide


@pytest.mark.asyncio
async def test_signin_card_uses_renderer():
    """6. test_signin_card_uses_renderer: RENDER_ENGINE=pillow returns image; RENDER_ENGINE=text returns Markdown."""
    await user_service.get_or_create_user(user_id="3001", username="card_user", gold=50, impression=2.0)

    # 6A. When RENDER_ENGINE = "pillow" -> output is PNG image
    config_service.set_global("RENDER_ENGINE", "pillow")
    replies_pillow = []

    async def _reply_fn_pillow(content):
        replies_pillow.append(content)
        return SentMessage(message_id=len(replies_pillow), content=content)

    actor = Actor(id=3001, username="card_user", full_name="Card User")
    chat = ChatRef(id=-10055, type="supergroup", title="Test Group")
    event = UnifiedEvent(actor=actor, chat=chat, text="签到", role=Role.MEMBER)
    ctx_pillow = CallContext(
        event=event,
        user=UserView(id="3001", level=0, gold=50, impression=2.0),
        group=GroupView(id="-10055", title="Test Group", level=5),
        reply_fn=_reply_fn_pillow,
    )

    await sign_in_plugin.handle_sign_in(ctx_pillow)
    assert len(replies_pillow) == 1
    content_pillow = replies_pillow[0]
    assert isinstance(content_pillow, bytes), "Pillow engine must return raw bytes to reply"
    assert content_pillow.startswith(b"\x89PNG\r\n\x1a\n"), "Must be a valid PNG image"

    # 6B. When RENDER_ENGINE = "text" -> output is Markdown text
    config_service.set_global("RENDER_ENGINE", "text")
    replies_text = []

    async def _reply_fn_text(content):
        replies_text.append(content)
        return SentMessage(message_id=len(replies_text), content=content)

    await user_service.get_or_create_user(user_id="3002", username="text_user", gold=50, impression=2.0)
    actor2 = Actor(id=3002, username="text_user", full_name="Text User")
    event2 = UnifiedEvent(actor=actor2, chat=chat, text="签到", role=Role.MEMBER)
    ctx_text = CallContext(
        event=event2,
        user=UserView(id="3002", level=0, gold=50, impression=2.0),
        group=GroupView(id="-10055", title="Test Group", level=5),
        reply_fn=_reply_fn_text,
    )

    await sign_in_plugin.handle_sign_in(ctx_text)
    assert len(replies_text) == 1
    content_text = replies_text[0]
    assert isinstance(content_text, str), "Text engine must return Markdown string"
    assert "签到成功" in content_text
    assert "获得金币" in content_text
