from typing import Any

from zxtg.core.render.port import RendererPort, RenderResult

INSTALL_GUIDE = "HTML 渲染依赖未安装，已降级；安装方法：pip install zxtg[html]"


class HtmlRenderer(RendererPort):
    """Optional HTML/Chromium renderer using Jinja2 and Playwright (FR-RND-04, FR-RND-06)."""

    @property
    def name(self) -> str:
        return "html"

    def is_available(self) -> tuple[bool, str | None]:
        try:
            import jinja2  # noqa: F401
            import playwright  # noqa: F401

            return True, None
        except ImportError:
            return False, INSTALL_GUIDE

    async def render(self, template: str, data: dict[str, Any]) -> RenderResult:
        avail, guide = self.is_available()
        if not avail:
            raise RuntimeError(guide or "HTML engine unavailable")

        from playwright.async_api import async_playwright

        html_content = f"<html><body><h1>{template}</h1><pre>{data}</pre></body></html>"
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html_content)
            img_bytes = await page.screenshot(type="png")
            await browser.close()

        return RenderResult(
            engine="html",
            content_type="image/png",
            content=img_bytes,
        )
