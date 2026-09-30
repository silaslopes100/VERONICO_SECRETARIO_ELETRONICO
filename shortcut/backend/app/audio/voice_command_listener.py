"""Captura do microfone do usuário e transcrição do comando de voz.

Grava PCM com ``sounddevice`` (WAV 16-bit), salva temporariamente e devolve o
texto transcrito pelo Whisper. Usado pelo botão "Responder" e pela esteira de
leitura sequencial ("sim", "próxima", "responder", "não"…).
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
import wave
from pathlib import Path
import numpy as np
import sounddevice as sd
from app.audio.whisper_transcriber import get_transcriber
from app.config import get_settings


logger = logging.getLogger(__name__)


class VoiceCaptureError(RuntimeError):
    """Erro de captura de áudio do microfone."""


def save_wav(path: Path, frames, sample_rate: int, channels: int) -> Path:
    """Grava frames int16 em um arquivo WAV."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return path


def record_seconds(seconds: float, sample_rate: int, channels: int):
    """Bloqueia por ``seconds`` gravando o microfone; devolve array int16.

    Usa callback + ``Event.wait`` com timeout duro (``seconds + 5``): se o
    dispositivo não entregar áudio, a gravação termina mesmo assim e o
    stream é liberado — ``sd.wait()`` podia pendurar para sempre.
    """
    logger.debug("Gravando %.1fs de áudio…", seconds)
    target = int(seconds * sample_rate)
    chunks: list[np.ndarray] = []
    got = {"n": 0}
    done = threading.Event()

    def callback(indata, _frames, _time, _status):  # noqa: ANN001 - assinatura do sounddevice
        if got["n"] >= target:
            done.set()
            return
        chunks.append(indata.copy())
        got["n"] += indata.shape[0]
        if got["n"] >= target:
            done.set()

    with sd.InputStream(
        samplerate=sample_rate, channels=channels, dtype="int16", callback=callback
    ):
        done.wait(timeout=seconds + 5)

    if not chunks:
        raise RuntimeError("microfone não entregou áudio dentro do tempo")
    recording = np.concatenate(chunks, axis=0)[:target]
    return recording.reshape(-1) if channels == 1 else recording


class VoiceCommandListener:
    """Ouve o usuário e devolve o comando transcrito."""

    def __init__(self) -> None:
        settings = get_settings()
        self.sample_rate = settings.audio_sample_rate
        self.channels = settings.audio_channels
        self.max_seconds = settings.audio_max_seconds

    def capture_wav(self, seconds: float | None = None) -> Path:
        """Grava o microfone e devolve o caminho do WAV temporário."""
        duration = min(seconds or 6.0, float(self.max_seconds))
        try:
            frames = record_seconds(duration, self.sample_rate, self.channels)
        except Exception as exc:  # noqa: BLE001
            raise VoiceCaptureError(f"Mic indisponível: {exc}") from exc
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp.close()
        return save_wav(Path(tmp.name), frames, self.sample_rate, self.channels)

    def listen(self, seconds: float | None = None) -> str:
        """Grava e transcreve o comando de voz do usuário."""
        path = self.capture_wav(seconds)
        try:
            text = get_transcriber().transcribe_safe(path, language="pt")
        finally:
            path.unlink(missing_ok=True)
        cleaned = text.strip()
        logger.info("Comando de voz: %r", cleaned)
        return cleaned

    async def listen_async(self, seconds: float | None = None) -> str:
        """Versão não bloqueante (roda o blocking I/O em worker thread)."""
        return await asyncio.to_thread(self.listen, seconds)


_listener: VoiceCommandListener | None = None


def get_voice_listener() -> VoiceCommandListener:
    global _listener
    if _listener is None:
        _listener = VoiceCommandListener()
    return _listener
