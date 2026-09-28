"""Transcrição de áudio com Whisper (faster-whisper, fallback openai-whisper).

O modelo é carregado sob demanda e mantido em memória (singleton) para que
mensagens recebidas e comandos de voz usem a mesma instância.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Erro na transcrição de áudio."""


class WhisperTranscriber:
    """Wrapper preguiçoso sobre o modelo Whisper."""

    def __init__(self) -> None:
        settings = get_settings()
        self.model_name = settings.whisper_model
        self.device = settings.whisper_device
        self.compute_type = settings.whisper_compute_type
        self._model = None
        self._backend = "none"

    # ------------------------------------------------------------------ model
    @property
    def backend(self) -> str:
        return self._backend

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore

            logger.info("Carregando faster-whisper (%s, %s)…", self.model_name, self.device)
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            self._backend = "faster-whisper"
        except Exception as exc:  # noqa: BLE001 - tenta fallback
            logger.warning("faster-whisper indisponível (%s); tentando openai-whisper.", exc)
            try:
                import whisper  # type: ignore

                self._model = whisper.load_model(self.model_name, device=self.device)
                self._backend = "openai-whisper"
            except Exception as exc2:  # noqa: BLE001
                raise TranscriptionError(
                    "Nenhum backend Whisper disponível. Instale `faster-whisper` "
                    f"(recomendado) ou `openai-whisper`. Detalhe: {exc2}"
                ) from exc2
        return self._model

    # ------------------------------------------------------------- transcribe
    def transcribe(self, source: str | Path | bytes, *, language: str | None = None) -> str:
        """Transcreve um arquivo de áudio (caminho ou bytes) em texto limpo."""
        path = self._to_file(source)
        try:
            text = self._transcribe_path(path, language)
        finally:
            if isinstance(source, (bytes, bytearray)) and path.exists():
                path.unlink(missing_ok=True)
        return text.strip()

    def _transcribe_path(self, path: Path, language: str | None) -> str:
        model = self._load_model()
        if self._backend == "faster-whisper":
            segments, _info = model.transcribe(str(path), language=language, vad_filter=True)
            return " ".join(seg.text for seg in segments)
        result = model.transcribe(str(path), language=language)
        return str(result.get("text", ""))

    @staticmethod
    def _to_file(source: str | Path | bytes) -> Path:
        if isinstance(source, (bytes, bytearray)):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
            tmp.write(bytes(source))
            tmp.close()
            return Path(tmp.name)
        path = Path(source)
        if not path.exists():
            raise TranscriptionError(f"Arquivo de áudio inexistente: {path}")
        return path

    def transcribe_safe(self, source: str | Path | bytes, *, language: str | None = None) -> str:
        """Versão tolerante a falhas: devolve string vazia em erro."""
        try:
            return self.transcribe(source, language=language)
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Transcrição falhou: %s", exc)
            return ""


_transcriber: WhisperTranscriber | None = None


def get_transcriber() -> WhisperTranscriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = WhisperTranscriber()
    return _transcriber
