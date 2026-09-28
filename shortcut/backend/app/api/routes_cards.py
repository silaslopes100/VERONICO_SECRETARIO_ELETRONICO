"""Endpoints REST dos cards e colunas do Kanban."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.kanban.flow_orchestrator import get_flow_orchestrator
from app.kanban.models import ColumnId
from app.kanban.state_manager import InvalidTransition, get_state_manager
from app.whatsapp.archiver import get_archiver
from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.inbox_reader import get_inbox_reader, sanitize_text
from app.whatsapp.message_sender import get_message_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["cards"])


class MoveRequest(BaseModel):
    column: ColumnId = Field(..., description="Coluna de destino")


class ReplyTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "shortcut-backend"}


@router.get("/state")
async def get_state() -> dict:
    """Estado completo do quadro Kanban."""
    return get_state_manager().snapshot()


@router.get("/status")
async def get_status() -> dict:
    """Status do WhatsApp, do fluxo de voz e da caixa de entrada."""
    return {
        "whatsapp": get_browser_manager().snapshot(),
        "flow": get_flow_orchestrator().status(),
        "unread": len(get_state_manager().cards_in(ColumnId.NEW)),
    }


@router.post("/cards/{card_id}/move")
async def move_card(card_id: str, payload: MoveRequest) -> dict:
    """Move um card entre colunas (valida a regra de transição)."""
    try:
        card = await get_state_manager().move_card(card_id, payload.column)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return card.to_dict()


@router.post("/cards/{card_id}/archive")
async def archive_card(card_id: str) -> dict:
    """Arquiva a conversa no WhatsApp e remove o card do quadro."""
    state = get_state_manager()
    card = state.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card inexistente")
    try:
        archived = await get_archiver().archive(card.contact)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not archived:
        raise HTTPException(status_code=502, detail="Falha ao arquivar no WhatsApp")
    removed = await state.archive_card(card_id)
    return {"archived": True, "card": removed.to_dict() if removed else None}


@router.post("/cards/{card_id}/reply-text")
async def reply_with_text(card_id: str, payload: ReplyTextRequest) -> dict:
    """Envia a transcrição da voz do usuário como texto na conversa.

    Usado pelo botão "Responder": o navegador grava o mic → ``/api/voice/transcribe``
    → este endpoint injeta o texto no WhatsApp via Playwright e avança o card
    para "Aguardando resposta" e, confirmado o envio, para "Respondidas".
    """
    state = get_state_manager()
    card = state.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card inexistente")
    text = sanitize_text(payload.text, 4000)
    if not text:
        raise HTTPException(status_code=422, detail="Texto vazio após sanitização")
    await state.set_reply(card.id, text)
    if card.column is ColumnId.HEARD:
        await state.move_card(card.id, ColumnId.WAITING_REPLY)
    try:
        sent = await get_message_sender().send_text(card.contact, text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not sent:
        raise HTTPException(status_code=502, detail="Falha ao enviar no WhatsApp")
    if state.column_of(card.id) is ColumnId.WAITING_REPLY:
        await state.move_card(card.id, ColumnId.RESPONDED)
    updated = state.get_card(card.id)
    return {"sent": True, "transcript": text, "card": updated.to_dict() if updated else None}


@router.post("/refresh")
async def refresh_inbox() -> dict:
    """Força uma leitura imediata da caixa de entrada."""
    new_cards = await get_inbox_reader().poll_once()
    return {"newCards": len(new_cards)}
