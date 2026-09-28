"""Endpoints de comando de voz, leitura sequencial e transcrição de áudio."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.audio.tts_speaker import get_speaker
from app.audio.voice_command_listener import VoiceCaptureError, get_voice_listener
from app.audio.whisper_transcriber import get_transcriber
from app.kanban.flow_orchestrator import get_flow_orchestrator
from app.kanban.state_manager import get_state_manager
from app.whatsapp.message_sender import get_message_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class ListenRequest(BaseModel):
    seconds: float = Field(6.0, ge=1.0, le=60.0)


class ReplyRequest(BaseModel):
    card_id: str = Field(..., alias="cardId")

    model_config = {"populate_by_name": True}


@router.post("/speak")
async def speak(payload: SpeakRequest) -> dict:
    """Sintetiza texto em fala no servidor (TTS local)."""
    ok = get_speaker().speak(payload.text)
    if not ok:
        raise HTTPException(status_code=422, detail="Texto vazio após normalização")
    return {"spoken": True}


@router.post("/listen")
async def listen(payload: ListenRequest) -> dict:
    """Grava o microfone e devolve o comando transcrito."""
    try:
        text = await get_voice_listener().listen_async(payload.seconds)
    except VoiceCaptureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"text": text}


@router.post("/transcribe")
async def transcribe(file: UploadFile) -> dict:
    """Transcreve um áudio enviado pelo navegador (botão Responder)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    try:
        text = get_transcriber().transcribe(data, language="pt")
    except Exception as exc:  # noqa: BLE001
        logger.error("Transcrição falhou: %s", exc)
        raise HTTPException(status_code=500, detail="Falha na transcrição") from exc
    return {"text": text.strip()}


@router.post("/reply")
async def reply(payload: ReplyRequest) -> dict:
    """Ouve a resposta do usuário, envia no WhatsApp e avança o card.

    Fluxo: mic → Whisper → texto → Playwright (campo de mensagem) → card
    passa para "Aguardando resposta" e, confirmado o envio, para "Respondidas".
    """
    state = get_state_manager()
    card = state.get_card(payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card inexistente")
    try:
        answer = await get_voice_listener().listen_async(seconds=10)
    except VoiceCaptureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not answer.strip():
        raise HTTPException(status_code=422, detail="Nenhum áudio reconhecido")
    await state.set_reply(card.id, answer)
    from app.kanban.models import ColumnId

    if card.column is ColumnId.HEARD:
        await state.move_card(card.id, ColumnId.WAITING_REPLY)
    try:
        sent = await get_message_sender().send_text(card.contact, answer)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not sent:
        raise HTTPException(status_code=502, detail="Falha ao enviar no WhatsApp")
    if state.column_of(card.id) is ColumnId.WAITING_REPLY:
        await state.move_card(card.id, ColumnId.RESPONDED)
    updated = state.get_card(card.id)
    return {"sent": True, "transcript": answer, "card": updated.to_dict() if updated else None}


@router.post("/announce")
async def announce() -> dict:
    """Fala 'Você tem X mensagens não lidas…' e espera confirmação por voz."""
    message = await get_flow_orchestrator().announce_unread()
    return {"message": message, "flow": get_flow_orchestrator().status()}


@router.post("/flow/start")
async def start_flow() -> dict:
    """Inicia a esteira de leitura sequencial dos cards."""
    await get_flow_orchestrator().start()
    return get_flow_orchestrator().status()


@router.post("/flow/stop")
async def stop_flow() -> dict:
    await get_flow_orchestrator().stop()
    return get_flow_orchestrator().status()


@router.get("/flow/status")
async def flow_status() -> dict:
    return get_flow_orchestrator().status()
