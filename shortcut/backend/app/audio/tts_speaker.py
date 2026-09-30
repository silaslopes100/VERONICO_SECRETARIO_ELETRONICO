"""Síntese de voz (texto → fala) para leitura de mensagens e prompts.

Usa ``pyttsx3`` (offline, driver SAPI5 no Windows / espeak no Linux) com
fallback silencioso quando não houver driver de áudio disponível.

Todo o acesso ao engine ``pyttsx3`` acontece na thread dedicada
``t-thread``: no Windows/SAPI5, criar o engine numa thread e chamar
``runAndWait()`` em outra retorna sem áudio e sem exceção. Por isso as
chamadas bloqueantes enfileiram a fala e aguardam um evento de conclusão.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
import time

from app.config import get_settings

logger = logging.getLogger(__name__)


def clean_for_speech(text: str) -> str:
    """Remove símbolos/URLs que atrapalham a leitura em voz alta."""
    if not text:
        return ""
    cleaned = re.sub(r"https?://\S+", " link ", text)
    cleaned = re.sub(r"[#*_>`~\[\]()]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class _Utterance:
    """Fala bloqueante: worker preenche ``done`` e sinaliza ``event``."""

    __slots__ = ("text", "event", "done")

    def __init__(self, text: str) -> None:
        self.text = text
        self.event = threading.Event()
        self.done = bool(False)


def _flush_sapi_events() -> None:
    """Descarta eventos SAPI pendentes (ex.: EndStream de fala purgada)."""
    try:
        import pythoncom  # type: ignore

        pythoncom.PumpWaitingMessages()
    except Exception:  # noqa: BLE001 - sem pythoncom (não-Windows) ou sem mensagens
        pass


class TTSSpeaker:
    """Fila única de fala — serializa as falas para não sobrepor."""

    def __init__(self) -> None:
        settings = get_settings()
        self.rate = settings.tts_rate
        self.voice_index = settings.tts_voice_index
        self._queue: queue.Queue[str | _Utterance | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._engine = None
        self._lock = threading.Lock()

    # -------------------------------------------------------------- lifecycle
    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, name="tts-worker", daemon=True)
        self._thread.start()

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        voices = engine.getProperty("voices") or []
        if 0 <= self.voice_index < len(voices):
            engine.setProperty("voice", voices[self.voice_index].id)
        self._engine = engine
        return engine

    def _say(self, text: str) -> bool:
        """Fala ``text`` — só pode ser chamado na thread ``tts-worker``.

        Corrige o bug de reuso do pyttsx3: sem ``setBusy(True)``, num engine
        já utilizado o ``say()`` executa imediatamente e o ``runAndWait()``
        seguinte purga a fala recém-enfileirada (modo "mudo" — retorna em
        ~0.1s sem áudio). Manter o proxy busy deixa o ``say`` na fila antes
        do ``endLoop``, igual a um engine recém-criado. Se ainda assim vier
        mudo, recria o engine e tenta de novo (até 3 tentativas).
        """
        long_text = len(text) > 60
        for attempt in range(1, 4):
            try:
                engine = self._get_engine()
                _flush_sapi_events()
                engine.proxy.setBusy(True)
                logger.debug("Falando: %.60r", text)
                started = time.monotonic()
                engine.say(text)
                engine.runAndWait()
                elapsed = time.monotonic() - started
            except Exception as exc:  # noqa: BLE001
                logger.warning("TTS indisponível (tentativa %d): %s", attempt, exc)
                self._engine = None
                continue
            if not (long_text and elapsed < 0.5):
                if attempt > 1:
                    logger.info("TTS falou na tentativa %d em %.1fs", attempt, elapsed)
                return True
            logger.warning(
                "TTS retornou mudo em %.2fs (tentativa %d, %d chars); recriando engine",
                elapsed,
                attempt,
                len(text),
            )
            self._engine = None
            time.sleep(0.1)
        logger.warning("TTS sem áudio após 3 tentativas: %.60r", text)
        return False

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                try:
                    if self._engine is not None:
                        self._engine.stop()
                except Exception:  # noqa: BLE001
                    pass
                break
            if isinstance(item, _Utterance):
                item.done = self._say(item.text)
                item.event.set()
            else:
                self._say(item)

    # ---------------------------------------------------------------- speak
    def speak(self, text: str) -> bool:
        """Enfileira ``text`` para ser falado (não bloqueia)."""
        speech = clean_for_speech(text)
        if not speech:
            logger.warning("TTS ignorado: texto vazio após normalização")
            return False
        self._ensure_thread()
        self._queue.put(speech)
        return True

    def speak_blocking(self, text: str) -> bool:
        """Enfileira ``text`` e aguarda a fala terminar (mesma thread do engine)."""
        speech = clean_for_speech(text)
        if not speech:
            logger.warning("TTS ignorado: texto vazio após normalização")
            return False
        utterance = _Utterance(speech)
        with self._lock:
            self._ensure_thread()
            self._queue.put(utterance)
            timeout = max(15.0, len(speech) / 2.0)
            started = time.monotonic()
            if not utterance.event.wait(timeout):
                logger.warning(
                    "TTS timeout após %.0fs falando: %.60r", timeout, speech
                )
                return False
            elapsed = time.monotonic() - started
        logger.info(
            "TTS done=%s em %.1fs (%d chars): %.60r",
            utterance.done,
            elapsed,
            len(speech),
            speech,
        )
        return utterance.done

    async def speak_async(self, text: str) -> bool:
        return await asyncio.to_thread(self.speak_blocking, text)

    def stop(self) -> None:
        if self._thread:
            self._queue.put(None)
            self._thread = None
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:  # noqa: BLE001
            pass


_speaker: TTSSpeaker | None = None


def get_speaker() -> TTSSpeaker:
    global _speaker
    if _speaker is None:
        _speaker = TTSSpeaker()
    return _speaker
