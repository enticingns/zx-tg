from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class RenderResult:
    """Immutable result of a rendering operation (FR-RND-01, FR-RND-05)."""

    engine: str
    content_type: str
    content: str | bytes
    notice: str | None = None

    @property
    def is_image(self) -> bool:
        return isinstance(self.content, bytes) or self.content_type.startswith("image/")

    @property
    def is_text(self) -> bool:
        return isinstance(self.content, str) or self.content_type.startswith("text/")


@runtime_checkable
class RendererPort(Protocol):
    """Abstract port for all rendering engines (FR-RND-01)."""

    @property
    def name(self) -> str:
        """Engine identifier name, e.g. 'text', 'pillow', 'html'."""
        ...

    def is_available(self) -> tuple[bool, str | None]:
        """Check if engine dependencies are present. Returns (available, install_guide)."""
        ...

    async def render(self, template: str, data: dict[str, Any]) -> RenderResult:
        """Render template with context data into RenderResult."""
        ...
