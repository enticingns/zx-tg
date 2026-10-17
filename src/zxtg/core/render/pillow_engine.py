import io
from typing import Any

from zxtg.core.render.port import RendererPort, RenderResult

INSTALL_GUIDE = "图片渲染引擎 Pillow 未安装，已降级为文本；安装方法：pip install zxtg[render]"


class PillowRenderer(RendererPort):
    """Lightweight card image renderer using Pillow (FR-RND-03, default engine)."""

    @property
    def name(self) -> str:
        return "pillow"

    def is_available(self) -> tuple[bool, str | None]:
        try:
            import PIL  # noqa: F401
            from PIL import Image, ImageDraw  # noqa: F401

            return True, None
        except ImportError:
            return False, INSTALL_GUIDE

    async def render(self, template: str, data: dict[str, Any]) -> RenderResult:
        avail, guide = self.is_available()
        if not avail:
            raise RuntimeError(guide or "Pillow engine unavailable")

        from PIL import Image, ImageDraw, ImageFont

        width, height = 480, 260
        img = Image.new("RGB", (width, height), color=(248, 250, 252))
        draw = ImageDraw.Draw(img)

        # Header decorative bar
        draw.rectangle([(0, 0), (width, 8)], fill=(59, 130, 246))

        # Title
        font = ImageFont.load_default()
        if template == "sign_in":
            title = "Daily Sign-In Reward"
            draw.text((30, 25), title, fill=(30, 41, 59), font=font)
            gold_reward = data.get("gold_reward", 0)
            current_gold = data.get("current_gold", 0)
            imp_reward = float(data.get("imp_reward", 0.0))
            current_imp = float(data.get("current_imp", 0.0))

            # Gold box
            draw.rounded_rectangle([(30, 65), (225, 175)], radius=8, fill=(254, 243, 199), outline=(245, 158, 11))
            draw.text((45, 80), "Gold Reward", fill=(146, 64, 14), font=font)
            draw.text((45, 110), f"+{gold_reward}", fill=(180, 83, 9), font=font)
            draw.text((45, 140), f"Balance: {current_gold}", fill=(146, 64, 14), font=font)

            # Impression box
            draw.rounded_rectangle([(255, 65), (450, 175)], radius=8, fill=(254, 226, 226), outline=(239, 68, 68))
            draw.text((270, 80), "Impression Reward", fill=(153, 27, 27), font=font)
            draw.text((270, 110), f"+{imp_reward:.1f}", fill=(185, 28, 28), font=font)
            draw.text((270, 140), f"Total: {current_imp:.1f}", fill=(153, 27, 27), font=font)

            draw.text((30, 210), f"User ID: {data.get('user_id', '')}", fill=(100, 116, 139), font=font)
        elif template == "sign_rank":
            title = str(data.get("title", "Leaderboard"))
            draw.text((30, 25), title, fill=(30, 41, 59), font=font)
            ranking = data.get("ranking", [])
            y = 65
            for idx, item in enumerate(ranking[:6], start=1):
                name = item.get("name", "Unknown")
                imp = float(item.get("impression", 0.0))
                draw.text((40, y), f"{idx}. {name} - {imp:.1f}", fill=(51, 65, 85), font=font)
                y += 26
        else:
            title = str(data.get("title", template))
            draw.text((30, 25), title, fill=(30, 41, 59), font=font)
            y = 70
            for k, v in list(data.items())[:6]:
                if k != "title":
                    draw.text((40, y), f"{k}: {v}", fill=(51, 65, 85), font=font)
                    y += 26

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        return RenderResult(
            engine="pillow",
            content_type="image/png",
            content=png_bytes,
        )
