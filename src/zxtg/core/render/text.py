from typing import Any

from zxtg.core.render.port import RendererPort, RenderResult


class TextRenderer(RendererPort):
    """Zero-dependency markdown text renderer (FR-RND-02, guaranteed fallback)."""

    @property
    def name(self) -> str:
        return "text"

    def is_available(self) -> tuple[bool, str | None]:
        return True, None

    async def render(self, template: str, data: dict[str, Any]) -> RenderResult:
        if template == "sign_in":
            gold_reward = data.get("gold_reward", 0)
            current_gold = data.get("current_gold", 0)
            imp_reward = float(data.get("imp_reward", 0.0))
            current_imp = float(data.get("current_imp", 0.0))
            content = (
                f"🎉 **签到成功！**\n"
                f"💰 获得金币：+{gold_reward}（当前余额：{current_gold}）\n"
                f"❤️ 获得好感度：+{imp_reward:.1f}（当前好感度：{current_imp:.1f}）"
            )
        elif template == "sign_rank":
            title = data.get("title", "好感度排行榜")
            ranking = data.get("ranking", [])
            lines = [f"🏆 **{title}**\n"]
            for idx, item in enumerate(ranking, start=1):
                name = item.get("name", "Unknown")
                imp = float(item.get("impression", 0.0))
                lines.append(f"{idx}. {name} - {imp:.1f}")
            content = "\n".join(lines)
        else:
            title = data.get("title", template)
            lines = [f"📋 **{title}**"]
            for k, v in data.items():
                if k != "title":
                    lines.append(f"- **{k}**: {v}")
            content = "\n".join(lines)

        return RenderResult(
            engine="text",
            content_type="text/markdown",
            content=content,
        )
