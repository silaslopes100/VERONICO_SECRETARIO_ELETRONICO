"""Orquestração do fluxo de voz: esteira de leitura e resposta sequencial.

Regra (documentada em docs/ARCHITECTURE.md):
- "sim" (variações)  → inicia a leitura da coluna **Nova mensagem**;
- "próxima"           → pula para o próximo card da fila;
- "responder"         → grava a resposta, envia no WhatsApp e avança o card;
- "arquivar"          → arquiva a conversa (card na coluna Respondidas);
- "não" / "parar"     → encerra o fluxo.
Comando vazio/ilegível após timeout avança automaticamente (esteira).
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from enum import Enum

from app.audio.tts_speaker import get_speaker
from app.audio.voice_command_listener import VoiceCaptureError, get_voice_listener
from app.audio.whisper_transcriber import get_transcriber
from app.kanban.models import Card, ColumnId
from app.kanban.state_manager import StateManager, get_state_manager
from app.whatsapp.archiver import get_archiver
from app.whatsapp.audio_extractor import get_audio_extractor
from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.message_sender import get_message_sender

logger = logging.getLogger(__name__)

AFFIRMATIONS = {"sim","sim!","sim.","yes", "isso", "pode ser", "vamos la", "confirma", "claro", "simsim"}
NEGATIONS = {"nao", "no", "para", "cancela", "cancelar", "parar", "stop"}
NEXT_WORDS = {"proxima", "proximo", "pula", "pular", "next", "seguir", "continua"}
REPLY_WORDS = {"responder", "responda", "reply", "resposta", "falar", "contestar"}
ARCHIVE_WORDS = {"arquivar", "archive", "arquiva"}


def normalize_command(text: str) -> str:
    """Minúsculas + remoção de acentos para comparação estável."""
    lowered = (text or "").strip().lower()
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn"
    )
    normalized = " ".join(stripped.split())
    logger.info("Normalized command: %s", normalized)
    return normalized
    


class Command(str, Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    NEXT = "next"
    REPLY = "reply"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


def classify_command(text: str) -> Command:
    """Mapeia a transcrição do usuário para um comando do fluxo."""
    normalized = normalize_command(text)
    logger.info("Classifying command from text: %s", normalized)
    if normalized == "":
        return Command.UNKNOWN
    words = set(normalized.split())
    phrase = normalized
    if any(phrase == a or phrase.startswith(a + " ") for a in AFFIRMATIONS) or words & {"sim", "yes"}:
        return Command.CONFIRM
    if words & AFFIRMATIONS:
        return Command.CONFIRM
    if words & NEGATIONS:
        return Command.REJECT
    if words & REPLY_WORDS:
        return Command.REPLY
    if words & NEXT_WORDS:
        return Command.NEXT
    if words & ARCHIVE_WORDS:
        return Command.ARCHIVE
    return Command.UNKNOWN


class FlowOrchestrator:
    """Esteira: ler → ouvir → (responder) → próximo card, um por vez."""

    def __init__(self, state: StateManager | None = None) -> None:
        self.state = state or get_state_manager()
        #self.speaker = get_speaker()
        self.listener = get_voice_listener()
        self.transcriber = get_transcriber()
        self.sender = get_message_sender()
        self.archiver = get_archiver()
        self.extractor = get_audio_extractor()
        self.speaker = get_speaker()
        self.active = False
        self.current_card_id: str | None = None
        self.last_command: str = ""
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        card = self.state.get_card(self.current_card_id) if self.current_card_id else None
        return {
            "active": self.active,
            "currentCardId": self.current_card_id,
            "currentContact": card.contact if card else None,
            "lastCommand": self.last_command,
            "whatsapp": get_browser_manager().status.value,
        }

    def _publish_status(self) -> None:
        from app.api.ws_gateway import publish

        publish({"type": "flow_status", "payload": self.status()})

    # -------------------------------------------------------------- entrypoint
    async def announce_unread(self) -> str:
        """Fala "Você tem X mensagens não lidas…" e escuta a confirmação."""
        count = len(self.state.cards_in(ColumnId.NEW))
        prompt = (
            f"Você tem {count} mensagens não lidas. Deseja ouvi-las agora?"
            if count
            else "Você não tem mensagens não lidas no momento."
        )
        await self.speaker.speak_async(prompt)
        if count == 0:
            return prompt
        try:
            answer = await asyncio.wait_for(
                self.listener.listen_async(seconds=5), timeout=20
            )
        except asyncio.TimeoutError:
            logger.warning("Escuta do anúncio travou após 20s; seguindo sem confirmação")
            answer = ""
        except VoiceCaptureError as exc:
            logger.warning("Mic indisponível: %s", exc)
            answer = ""
        command = classify_command(answer)
        logger.info("Commando classificado: %s", command)
        logger.info("Resposta do usuário: %s", answer)
        self.last_command = answer
        if command is Command.CONFIRM:
            await self.start()
            return f"Iniciando leitura de {count} mensagens."
        return f"Comando não reconhecido: {answer or 'silêncio'}"

    async def start(self) -> None:
        """Inicia (ou retoma) a esteira de leitura sequencial."""
        if self.active:
            logger.info("Esteira já ativa; start ignorado")
            return
        self.active = True
        self._publish_status()
        self._task = asyncio.create_task(self._run(), name="kanban-flow")

    async def stop(self) -> None:
        self.active = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.current_card_id = None
        self._publish_status()

    # -------------------------------------------------------------------- loop
    async def _run(self) -> None:
        processed: set[str] = set()
        try:
            while self.active:
                card = self._next_pending(processed)
                if card is None:
                    await self.speaker.speak_async("Fila vazia. Nenhuma mensagem para ler.")
                    break
                processed.add(card.id)
                await self._process_card(card)
        except asyncio.CancelledError:
            logger.debug("Fluxo cancelado.")
        except Exception:
            logger.exception("Erro na esteira de leitura")
        finally:
            self.active = False
            self.current_card_id = None
            self._publish_status()

    def _next_pending(self, processed: set[str]) -> Card | None:
        """Próximo card ainda não processado (Nova mensagem, depois Ouvidas)."""
        for column in (ColumnId.NEW, ColumnId.HEARD):
            for card in self.state.cards_in(column):
                if card.id not in processed:
                    return card
        return None

    async def _process_card(self, card: Card) -> None:
        self.current_card_id = card.id
        self._publish_status()
        logger.info("Processando card %s (%s)", card.id, card.contact)

        transcript = await self._ensure_transcript(card)
        speech = f"Mensagem de {card.contact}. {transcript}"
        logger.info("Falando card %s: %.80r", card.id, speech)
        await self.speaker.speak_async(speech)

        if card.column is ColumnId.NEW:
            await self.state.move_card(card.id, ColumnId.HEARD)
            card = self.state.get_card(card.id) or card

        command = await self._listen_command()
        await self._apply_command(card, command)

    async def _ensure_transcript(self, card: Card) -> str:
        """Transcreve o áudio recebido (se for o caso) e retorna o texto."""
        if card.transcript:
            return card.transcript
        if card.is_audio:
            try:
                path = await self.extractor.download_latest(card.contact)
                if path:
                    text = await asyncio.to_thread(
                        self.transcriber.transcribe_safe, path, language="pt"
                    )
                    if text:
                        await self.state.set_transcript(card.id, text)
                        return text
            except Exception as exc:  # noqa: BLE001
                logger.warning("Transcrição do áudio falhou: %s", exc)
        return card.speech_text

    async def _listen_command(self, timeout: float = 5.0) -> Command:
        logger.info("Escutando comando por %.0fs…", timeout)
        try:
            answer = await asyncio.wait_for(
                self.listener.listen_async(seconds=timeout),
                timeout=timeout + 15,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Escuta travou após %.0fs; seguindo sem comando", timeout + 15
            )
            answer = ""
        except VoiceCaptureError as exc:
            logger.warning("Não foi possível ouvir o usuário: %s", exc)
            return Command.NEXT  # esteira segue sem comando
        command = classify_command(answer)
        if command is Command.UNKNOWN and not answer.strip():
            command = Command.NEXT
        self.last_command = answer or command.value
        self._publish_status()
        return command

    async def _apply_command(self, card: Card, command: Command) -> None:
        if command is Command.REJECT:
            await self.speaker.speak_async("Fluxo encerrado.")
            await self.stop()
            return
        if command is Command.ARCHIVE:
            await self._archive(card)
            return
        if command is Command.REPLY:
            await self._reply(card)
            return
        # NEXT ou UNKNOWN → esteira segue para o próximo card
        self.current_card_id = None
        self._publish_status()

    # ---------------------------------------------------------------- actions
    async def _reply(self, card: Card) -> None:
        await self.speaker.speak_async("Pode falar a sua resposta.")
        try:
            answer = await asyncio.wait_for(
                self.listener.listen_async(seconds=10), timeout=25
            )
        except asyncio.TimeoutError:
            logger.warning("Escuta da resposta travou após 25s")
            answer = ""
        except VoiceCaptureError as exc:
            logger.warning("Falha ao capturar resposta: %s", exc)
            await self.speaker.speak_async("Não consegui ouvir. Vamos para a próxima.")
            return
        if not answer.strip():
            await self.speaker.speak_async("Resposta vazia. Vamos para a próxima.")
            return
        await self.state.set_reply(card.id, answer)
        if card.column is ColumnId.HEARD:
            await self.state.move_card(card.id, ColumnId.WAITING_REPLY)
        try:
            sent = await self.sender.send_text(card.contact, answer)
        except Exception as exc:  # noqa: BLE001
            logger.error("Envio falhou: %s", exc)
            await self.speaker.speak_async("Não consegui enviar a resposta.")
            return
        if sent:
            if self.state.column_of(card.id) is ColumnId.WAITING_REPLY:
                await self.state.move_card(card.id, ColumnId.RESPONDED)
            await self.speaker.speak_async(f"Resposta enviada para {card.contact}.")
        self.current_card_id = None
        self._publish_status()

    async def _archive(self, card: Card) -> None:
        try:
            ok = await self.archiver.archive(card.contact)
        except Exception as exc:  # noqa: BLE001
            logger.error("Arquivamento falhou: %s", exc)
            ok = False
        if ok:
            await self.state.archive_card(card.id)
            await self.speaker.speak_async(f"Conversa com {card.contact} arquivada.")
        self.current_card_id = None
        self._publish_status()


_orchestrator: FlowOrchestrator | None = None


def get_flow_orchestrator() -> FlowOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = FlowOrchestrator()
    return _orchestrator
