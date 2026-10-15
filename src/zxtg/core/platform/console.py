import logging
import sys

from zxtg.core.context import CallContext, SentMessage, UserView
from zxtg.core.event import Actor, ChatRef, Role, UnifiedEvent
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.platform.base import PlatformAdapter

logger = logging.getLogger("zxtg.platform.console")


class ConsoleAdapter(PlatformAdapter):
    """Console debugging adapter for M0 smoke testing without Telegram (Design §2.1)."""

    def __init__(self) -> None:
        self._running = False
        self.last_replies: list[str] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, target: str, content: str) -> SentMessage:
        self.last_replies.append(str(content))
        logger.info("Bot -> %s", content)
        return SentMessage(message_id=len(self.last_replies), content=content)

    async def process_line(self, line: str) -> list[str]:
        """Process a single input line, execute through pipeline, and return replies."""
        cleaned = line.strip()
        if not cleaned:
            return []

        actor = Actor(id="console_user", full_name="Console User", username="console")
        chat = ChatRef(id="console_chat", type="private", title="Console")
        event = UnifiedEvent(
            actor=actor,
            chat=chat,
            role=Role.OWNER,
            kind="command" if cleaned.startswith("/") else "text",
            text=cleaned,
            message_id=1,
        )

        async def _reply_callback(content: str) -> SentMessage:
            return await self.send("console_user", content)

        user_view = UserView(id="console_user", level=Role.OWNER.level, gold=1000, impression=100.0)
        ctx = CallContext(event=event, user=user_view, reply_fn=_reply_callback)

        await run_pipeline(ctx)
        return list(self.last_replies)

    async def run_once(self) -> None:
        """Read a line from stdin, process it, and log output."""
        line = sys.stdin.readline()
        if line:
            await self.process_line(line)
