"""Entidades do quadro Kanban (cards, colunas, conversas)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ColumnId(str, Enum):
    """Colunas fixas do fluxo, na ordem do processo."""

    NEW = "new"                      # Nova mensagem
    HEARD = "heard"                  # Ouvidas
    WAITING_REPLY = "waiting_reply"  # Aguardando resposta
    RESPONDED = "responded"          # Respondidas


COLUMN_ORDER: list[ColumnId] = [
    ColumnId.NEW,
    ColumnId.HEARD,
    ColumnId.WAITING_REPLY,
    ColumnId.RESPONDED,
]

COLUMN_TITLES: dict[ColumnId, str] = {
    ColumnId.NEW: "Nova mensagem",
    ColumnId.HEARD: "Ouvidas",
    ColumnId.WAITING_REPLY: "Aguardando resposta",
    ColumnId.RESPONDED: "Respondidas",
}


@dataclass
class Column:
    """Coluna do Kanban com a lista ordenada de card ids."""

    id: ColumnId
    title: str
    card_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id.value, "title": self.title, "cardIds": list(self.card_ids)}


@dataclass
class Card:
    """Um card representa uma conversa do WhatsApp em um estágio do fluxo."""

    chat_id: str
    contact: str
    preview: str
    timestamp: str = ""
    column: ColumnId = ColumnId.NEW
    transcript: str = ""
    reply_text: str = ""
    is_audio: bool = False
    unread_count: int = 1
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    archived: bool = False

    @property
    def speech_text(self) -> str:
        """Texto lido em voz alta pelo TTS (transcrição ou preview)."""
        return self.transcript or self.preview or "mensagem sem conteúdo"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chatId": self.chat_id,
            "contact": self.contact,
            "preview": self.preview,
            "timestamp": self.timestamp,
            "column": self.column.value,
            "transcript": self.transcript,
            "replyText": self.reply_text,
            "isAudio": self.is_audio,
            "unreadCount": self.unread_count,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Card":
        return cls(
            chat_id=data.get("chat_id") or data.get("chatId", ""),
            contact=data.get("contact", ""),
            preview=data.get("preview", ""),
            timestamp=data.get("timestamp", ""),
            column=ColumnId(data.get("column", ColumnId.NEW.value)),
            transcript=data.get("transcript", ""),
            reply_text=data.get("reply_text") or data.get("replyText", ""),
            is_audio=bool(data.get("is_audio") or data.get("isAudio")),
            unread_count=int(data.get("unread_count") or data.get("unreadCount") or 1),
            id=data.get("id") or uuid.uuid4().hex[:12],
            created_at=float(data.get("created_at") or data.get("createdAt") or time.time()),
            updated_at=float(data.get("updated_at") or data.get("updatedAt") or time.time()),
            archived=bool(data.get("archived")),
        )


@dataclass
class Conversation:
    """Ponte entre a leitura do WhatsApp e o card do Kanban."""

    chat_id: str
    name: str
    preview: str
    timestamp: str = ""
    is_audio: bool = False
    unread_count: int = 1

    def to_card(self) -> Card:
        return Card(
            chat_id=self.chat_id,
            contact=self.name,
            preview=self.preview,
            timestamp=self.timestamp,
            is_audio=self.is_audio,
            unread_count=self.unread_count,
        )


def build_columns() -> dict[ColumnId, Column]:
    """Cria as 4 colunas fixas vazias na ordem do fluxo."""
    return {cid: Column(id=cid, title=COLUMN_TITLES[cid]) for cid in COLUMN_ORDER}
