from abc import ABC, abstractmethod
from typing import Any


class PlatformAdapter(ABC):
    """Abstract interface for platform adapters (Design §2.1 L1)."""

    @abstractmethod
    async def start(self) -> None:
        """Start adapter receiving loops or listeners."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop adapter."""
        ...

    @abstractmethod
    async def send(self, target: Any, content: Any) -> Any:
        """Deliver content to platform destination."""
        ...
