import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ChatSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    conversation_id: Optional[str] = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    draft: str = ""
    include_context: bool = True
    updated_at: str = ""

    @property
    def title(self) -> str:
        return next((text for role, text in self.messages if role == "Tu"), self.draft or "Nuova chat")


class ChatHistory:
    def __init__(self, directory: str, vault: Optional[str]) -> None:
        key = hashlib.sha256(os.path.realpath(vault or directory).encode()).hexdigest()[:16]
        self.directory = Path(directory) / key
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def load(self, chat_id: str) -> Optional[ChatSession]:
        if len(chat_id) != 32 or any(char not in "0123456789abcdef" for char in chat_id):
            return None
        try:
            data = json.loads((self.directory / f"{chat_id}.json").read_text())
            if not isinstance(data, dict) or data.get("id") != chat_id:
                return None
            messages = data.get("messages", [])
            if not isinstance(messages, list) or any(not isinstance(message, list) or len(message) != 2
                    or not all(isinstance(value, str) for value in message) for message in messages):
                return None
            conversation_id = data.get("conversation_id")
            if conversation_id is not None and not isinstance(conversation_id, str):
                return None
            if not isinstance(data.get("draft", ""), str) or not isinstance(data.get("updated_at", ""), str):
                return None
            return ChatSession(chat_id, conversation_id, [(role, text) for role, text in messages],
                data.get("draft", ""), bool(data.get("include_context", True)), data.get("updated_at", ""))
        except (OSError, ValueError):
            return None

    def latest(self) -> Optional[ChatSession]:
        try:
            chat_id = (self.directory / "active").read_text().strip()
        except (OSError, ValueError):
            return None
        return self.load(chat_id)

    def entries(self) -> list[ChatSession]:
        chats = [chat for path in self.directory.glob("*.json") if (chat := self.load(path.stem))
            and (chat.messages or chat.draft or chat.conversation_id)]
        return sorted(chats, key=lambda chat: chat.updated_at, reverse=True)

    def save(self, chat: ChatSession) -> None:
        chat.updated_at = datetime.now(timezone.utc).isoformat()
        target = self.directory / f"{chat.id}.json"
        temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(asdict(chat), ensure_ascii=False))
            os.replace(temporary, target)
            active = self.directory / f"active.{uuid.uuid4().hex}.tmp"
            active.write_text(chat.id)
            os.replace(active, self.directory / "active")
        finally:
            temporary.unlink(missing_ok=True)
