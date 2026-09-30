"""Testes do StateManager: atualização/reabertura de cards existentes."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.kanban.models import ColumnId, Conversation
from app.kanban.state_manager import StateManager


def make_state(tmp_path: Path) -> StateManager:
    return StateManager(persist_path=tmp_path / "kanban.json")


def spy_broadcast(state: StateManager) -> list[int]:
    calls: list[int] = []
    state._broadcast = lambda: calls.append(1)  # type: ignore[method-assign]
    return calls


async def add_card(state: StateManager, **kwargs) -> object:
    data: dict = {"chat_id": "maria", "name": "Maria", "preview": "Olá"}
    data.update(kwargs)
    transcript = data.pop("transcript", "")
    card = await state.add_conversation(Conversation(**data))
    assert card is not None
    if transcript:
        card.transcript = transcript
    return card


class TestUpdateConversation:
    async def test_sem_card_retorna_none(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        result = await state.update_conversation(Conversation(chat_id="x", name="X", preview="oi"))
        assert result is None

    async def test_atualiza_preview_e_reabre_em_new(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state)
        await state.move_card(card.id, ColumnId.HEARD)
        calls = spy_broadcast(state)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Novo assunto", timestamp="10:05")
        )

        assert updated is not None
        assert updated.preview == "Novo assunto"
        assert updated.timestamp == "10:05"
        assert updated.column is ColumnId.NEW
        assert state.columns[ColumnId.NEW].card_ids == [card.id]
        assert state.columns[ColumnId.HEARD].card_ids == []
        assert len(calls) == 1

    async def test_sem_mudanca_nao_publica(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state, timestamp="09:12")
        await state.move_card(card.id, ColumnId.HEARD)
        calls = spy_broadcast(state)

        result = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Olá", timestamp="09:12")
        )

        assert result is not None
        assert result.column is ColumnId.HEARD  # não reabre sem mudança real
        assert calls == []

    async def test_migracao_adota_chat_id_novo_por_nome(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state, chat_id="maria-0")  # id antigo (slug + índice)
        await state.move_card(card.id, ColumnId.HEARD)
        calls = spy_broadcast(state)

        updated = await state.update_conversation(
            Conversation(chat_id="jid:5511999999999@c.us", name="Maria", preview="Olá")
        )

        assert updated is not None
        assert updated.id == card.id  # mesmo card, sem duplicar
        assert updated.chat_id == "jid:5511999999999@c.us"
        assert updated.column is ColumnId.HEARD  # migração de id não é mensagem nova
        assert len(calls) == 1

    async def test_somente_hora_mudou_nao_reabre(self, tmp_path: Path) -> None:
        """'Hoje' vira 'ontem' sem mensagem nova — republica, mas não reabre."""
        state = make_state(tmp_path)
        card = await add_card(state, timestamp="hoje")
        await state.move_card(card.id, ColumnId.HEARD)
        calls = spy_broadcast(state)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Olá", timestamp="ontem")
        )

        assert updated is not None
        assert updated.column is ColumnId.HEARD
        assert updated.timestamp == "ontem"
        assert len(calls) == 1

    async def test_badge_incrementado_reabre(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state, unread_count=1)
        await state.move_card(card.id, ColumnId.HEARD)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Olá", unread_count=3)
        )

        assert updated is not None
        assert updated.column is ColumnId.NEW
        assert updated.unread_count == 3

    async def test_preview_proprio_nao_reabre(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state, transcript="transcrição antiga")
        await state.move_card(card.id, ColumnId.HEARD)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Você: tudo bem")
        )

        assert updated is not None
        assert updated.column is ColumnId.HEARD
        assert updated.preview == "Você: tudo bem"
        assert updated.transcript == "transcrição antiga"  # resposta própria não invalida

    async def test_mensagem_nova_limpa_transcript(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        await add_card(state, transcript="transcrição antiga", is_audio=True)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Áudio novo", is_audio=True)
        )

        assert updated is not None
        assert updated.transcript == ""
        assert updated.is_audio is True

    async def test_reabre_desde_responded(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state)
        await state.move_card(card.id, ColumnId.WAITING_REPLY)
        await state.move_card(card.id, ColumnId.RESPONDED)

        updated = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Mais uma mensagem")
        )

        assert updated is not None
        assert updated.column is ColumnId.NEW  # bypass ALLOWED_TRANSITIONS de propósito
        assert state.columns[ColumnId.RESPONDED].card_ids == []

    async def test_card_arquivado_nao_reativa(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        card = await add_card(state)
        await state.archive_card(card.id)

        result = await state.update_conversation(
            Conversation(chat_id="maria", name="Maria", preview="Oi de novo")
        )
        assert result is None  # chamador deve criar card novo
