import logging
from typing import Any

from zxtg.core.render.html import HtmlRenderer
from zxtg.core.render.pillow_engine import PillowRenderer
from zxtg.core.render.port import RendererPort, RenderResult
from zxtg.core.render.text import TextRenderer

logger = logging.getLogger("zxtg.render")

DEGRADATION_CHAIN = {
    "html": "pillow",
    "pillow": "text",
    "text": None,
}


class RenderRegistry:
    """Registry managing renderer discovery, engine selection, and observable degradation (FR-RND-01, FR-RND-05, FR-RND-07)."""

    def __init__(self) -> None:
        self._renderers: dict[str, RendererPort] = {
            "text": TextRenderer(),
            "pillow": PillowRenderer(),
            "html": HtmlRenderer(),
        }
        self._warned_engines: set[str] = set()

    def get(self, name: str) -> RendererPort | None:
        return self._renderers.get(name)

    def register(self, renderer: RendererPort) -> None:
        self._renderers[renderer.name] = renderer

    def clear_warned(self) -> None:
        """Reset warning state for test repeatability."""
        self._warned_engines.clear()

    async def render(
        self,
        template: str,
        data: dict[str, Any],
        engine: str | None = None,
    ) -> RenderResult:
        current_engine = (engine or "pillow").lower()
        if current_engine not in self._renderers:
            logger.warning("Unknown render engine '%s', falling back to text", current_engine)
            current_engine = "text"

        requested_engine = current_engine
        notice: str | None = None

        while current_engine:
            renderer = self._renderers[current_engine]
            avail, guide = renderer.is_available()

            if avail:
                try:
                    res = await renderer.render(template, data)
                    # Notice is attached if this operation resulted from a degradation
                    if notice and res.notice is None:
                        res = RenderResult(
                            engine=res.engine,
                            content_type=res.content_type,
                            content=res.content,
                            notice=notice,
                        )
                    return res
                except Exception as exc:
                    logger.warning(
                        "Rendering failed on engine '%s' (%s); degrading to next tier",
                        current_engine,
                        exc,
                    )

            # Not available or failed: record warning and compute degradation guide
            next_engine = DEGRADATION_CHAIN.get(current_engine)
            logger.warning(
                "Render engine '%s' is unavailable (%s); degrading to '%s'",
                current_engine,
                guide or "runtime failure",
                next_engine or "none",
            )

            if requested_engine not in self._warned_engines:
                self._warned_engines.add(requested_engine)
                notice = guide or f"渲染引擎 {requested_engine} 不可用，已降级为 {next_engine}"

            if not next_engine:
                break
            current_engine = next_engine

        # Absolute fallback to TextRenderer guaranteeing no business crash (FR-RND-05)
        text_renderer = self._renderers["text"]
        res = await text_renderer.render(template, data)
        return RenderResult(
            engine="text",
            content_type=res.content_type,
            content=res.content,
            notice=notice,
        )


render_registry = RenderRegistry()


async def render_with_fallback(
    template: str,
    data: dict[str, Any],
    engine: str | None = None,
) -> RenderResult:
    return await render_registry.render(template, data, engine=engine)
