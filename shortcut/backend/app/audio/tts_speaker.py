"""Síntese de voz (texto → fala) para leitura de mensagens e prompts.

Usa ``pyttsx3`` (offline, driver SAPI5 no Windows / espeak no Linux) com
fallback silencioso quando não houver driver de áudio disponível.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading

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


class TTSSpeaker:
    """Fila única de fala — serializa as falas para não sobrepor."""

    def __init__(self) -> None:
        settings = get_settings()
        self.rate = settings.tts_rate
        self.voice_index = settings.tts_voice_index
        self._queue: queue.Queue[str | None] = queue.Queue()
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

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                engine = self._get_engine()
                engine.say(item)
                engine.runAndWait()
            except Exception as exc:  # noqa: BLE001
                logger.warning("TTS indisponível: %s", exc)
                self._engine = None

    # ---------------------------------------------------------------- speak
    def speak(self, text: str) -> bool:
        """Enfileira ``text`` para ser falado (não bloqueia)."""
        speech = clean_for_speech(text)
        if not speech:
            return False
        self._ensure_thread()
        self._queue.put(speech)
        return True

    def speak_blocking(self, text: str) -> bool:
        speech = clean_for_speech(text)
        if not speech:
            return False
        with self._lock:
            try:
                engine = self._get_engine()
                engine.say(speech)
                engine.runAndWait()
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("TTS indisponível: %s", exc)
                return False

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
