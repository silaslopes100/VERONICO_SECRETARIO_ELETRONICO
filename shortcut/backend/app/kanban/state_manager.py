"""Estado do quadro Kanban: posição dos cards, transições e persistência.

Toda mutação publica um evento ``kanban_state`` via WebSocket para o frontend
refletir em tempo real.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.kanban.models import COLUMN_ORDER, Card, ColumnId, Conversation, build_columns

logger = logging.getLogger(__name__)

# Transições permitidas: avanço no fluxo ou um passo atrás (correção manual).
ALLOWED_TRANSITIONS: dict[ColumnId, set[ColumnId]] = {
    ColumnId.NEW: {ColumnId.HEARD, ColumnId.WAITING_REPLY},
    ColumnId.HEARD: {ColumnId.NEW, ColumnId.WAITING_REPLY},
    ColumnId.WAITING_REPLY: {ColumnId.HEARD, ColumnId.RESPONDED},
    ColumnId.RESPONDED: {ColumnId.WAITING_REPLY},
}


class InvalidTransition(ValueError):
    """Movimento de coluna não permitido pela regra do fluxo."""


class StateManager:
    """Guarda a fonte de verdade do Kanban (memória + espelho em JSON)."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.persist_path = persist_path or (self.settings.data_dir / "kanban.json")
        self.columns = build_columns()
        self.cards: dict[str, Card] = {}
        self._lock = asyncio.Lock()
        self._load()

    # ------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            raw = json.loads(self.persist_path.read_text("utf-8"))
            self.cards = {c["id"]: Card.from_dict(c) for c in raw.get("cards", [])}
            order = [ColumnId(cid) for cid in raw.get("order", [])] or COLUMN_ORDER
            for cid in COLUMN_ORDER:
                self.columns[cid].card_ids = []
            for cid in order:
                if cid in self.columns:
                    self.columns[cid].card_ids = [
                        i for i in raw.get("columns", {}).get(cid.value, []) if i in self.cards
                    ]
            logger.info("Estado do Kanban restaurado (%d cards).", len(self.cards))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao restaurar kanban.json: %s", exc)

    def _save(self) -> None:
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "cards": [c.to_dict() for c in self.cards.values()],
                "columns": {cid.value: list(col.card_ids) for cid, col in self.columns.items()},
                "order": [cid.value for cid in COLUMN_ORDER],
                "saved_at": time.time(),
            }
            self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao persistir kanban.json: %s", exc)

    # ------------------------------------------------------------------ events
    def _broadcast(self) -> None:
        from app.api.ws_gateway import publish  # import tardio evita ciclo

        publish({"type": "kanban_state", "payload": self.snapshot()})

    # ------------------------------------------------------------------ queries
    def snapshot(self) -> dict[str, Any]:
        return {
            "columns": [self.columns[cid].to_dict() for cid in COLUMN_ORDER],
            "cards": {cid: card.to_dict() for cid, card in self.cards.items()},
            "unreadCount": len(self.columns[ColumnId.NEW].card_ids),
            "updatedAt": time.time(),
        }

    def get_card(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    def column_of(self, card_id: str) -> ColumnId | None:
        card = self.cards.get(card_id)
        return card.column if card else None

    def cards_in(self, column: ColumnId) -> list[Card]:
        return [self.cards[cid] for cid in self.columns[column].card_ids if cid in self.cards]

    def next_new_card(self) -> Card | None:
        """Primeiro card da coluna "Nova mensagem" (ordem exibida)."""
        queue = self.cards_in(ColumnId.NEW)
        return queue[0] if queue else None

    # ---------------------------------------------------------------- mutations
    async def add_conversation(self, conversation: Conversation) -> Card | None:
        """Cria card a partir de conversa não lida (ignora duplicados)."""
        async with self._lock:
            existing = next(
                (c for c in self.cards.values() if c.chat_id == conversation.chat_id and not c.archived),
                None,
            )
            if existing:
                existing.unread_count = max(existing.unread_count, conversation.unread_count)
                existing.updated_at = time.time()
                self._save()
                self._broadcast()
                return existing
            card = conversation.to_card()
            self.cards[card.id] = card
            self.columns[ColumnId.NEW].card_ids.append(card.id)
            self._save()
            self._broadcast()
            logger.info("Card criado: %s (%s)", card.contact, card.id)
            return card

    async def update_conversation(self, conversation: Conversation) -> Card | None:
        """Atualiza card existente; reabre em "Nova mensagem" se chegou mensagem.

        Casa primeiro por ``chat_id`` e, na falta, por nome do contato (migração
        de ids antigos sem índice). Retorna ``None`` quando não há card — o
        chamador deve então criar um. Idempotente: sem mudança real não publica.

        Só há reabertura quando a mudança indica mensagem **recebida** (preview
        novo ou badge incrementado) — migração de id, hora "hoje/ontem" ou
        resposta própria ("Você: …") apenas republicam o card no lugar.
        """
        async with self._lock:
            existing = next(
                (c for c in self.cards.values() if c.chat_id == conversation.chat_id and not c.archived),
                None,
            )
            if existing is None:
                existing = next(
                    (c for c in self.cards.values() if c.contact == conversation.name and not c.archived),
                    None,
                )
            if existing is None:
                return None

            preview = conversation.preview
            is_self = preview.lower().startswith(("você:", "voce:", "you:"))
            republish = False
            message_received = False

            if existing.chat_id != conversation.chat_id:
                logger.info(
                    "Card %s adotou chat_id %s (migração de id antigo)",
                    existing.id,
                    conversation.chat_id,
                )
                existing.chat_id = conversation.chat_id
                republish = True
            if preview and preview != existing.preview:
                existing.preview = preview
                existing.is_audio = conversation.is_audio
                if not is_self:
                    existing.transcript = ""  # mensagem nova invalida transcrição antiga
                    message_received = True
                republish = True
            if conversation.timestamp and conversation.timestamp != existing.timestamp:
                existing.timestamp = conversation.timestamp
                republish = True
            if conversation.unread_count and conversation.unread_count != existing.unread_count:
                existing.unread_count = conversation.unread_count
                republish = True
                if not is_self:
                    message_received = True

            if not republish:
                return existing

            if message_received and existing.column is not ColumnId.NEW:
                self.columns[existing.column].card_ids.remove(existing.id)
                existing.column = ColumnId.NEW
                self.columns[ColumnId.NEW].card_ids.append(existing.id)
                logger.info(
                    "Card %s reaberto em Nova mensagem (%s)",
                    existing.id,
                    existing.contact,
                )
            existing.updated_at = time.time()
            self._save()
            self._broadcast()
            return existing

    async def move_card(self, card_id: str, target: ColumnId) -> Card:
        """Move o card validando a transição; publica o novo estado."""
        async with self._lock:
            card = self.cards.get(card_id)
            if card is None:
                raise KeyError(f"Card inexistente: {card_id}")
            if card.column is target:
                return card
            if target not in ALLOWED_TRANSITIONS[card.column]:
                raise InvalidTransition(f"{card.column.value} → {target.value} não permitido")
            self.columns[card.column].card_ids.remove(card_id)
            card.column = target
            card.updated_at = time.time()
            self.columns[target].card_ids.append(card_id)
            self._save()
            self._broadcast()
            logger.info("Card %s movido para %s", card_id, target.value)
            return card

    async def set_transcript(self, card_id: str, transcript: str) -> Card:
        async with self._lock:
            card = self.cards.get(card_id)
            if card is None:
                raise KeyError(f"Card inexistente: {card_id}")
            card.transcript = transcript
            card.updated_at = time.time()
            self._save()
            self._broadcast()
            return card

    async def set_reply(self, card_id: str, reply_text: str) -> Card:
        async with self._lock:
            card = self.cards.get(card_id)
            if card is None:
                raise KeyError(f"Card inexistente: {card_id}")
            card.reply_text = reply_text
            card.updated_at = time.time()
            self._save()
            self._broadcast()
            return card

    async def archive_card(self, card_id: str) -> Card | None:
        """Remove o card do quadro (conversa arquivada no WhatsApp)."""
        async with self._lock:
            card = self.cards.get(card_id)
            if card is None:
                return None
            card.archived = True
            card.updated_at = time.time()
            column = self.columns[card.column]
            if card_id in column.card_ids:
                column.card_ids.remove(card_id)
            self._save()
            self._broadcast()
            return card


_state: StateManager | None = None


def get_state_manager() -> StateManager:
    global _state
    if _state is None:
        _state = StateManager()
    return _state
