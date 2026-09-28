"""Testes do transcritor Whisper (sem carregar o modelo real)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.audio.whisper_transcriber import TranscriptionError, WhisperTranscriber


def test_to_file_grava_bytes(tmp_path: Path) -> None:
    path = WhisperTranscriber._to_file(b"OggS....conteudo....")
    try:
        assert path.exists()
        assert path.read_bytes().startswith(b"OggS")
    finally:
        path.unlink(missing_ok=True)


def test_to_file_arquivo_inexistente_levanta() -> None:
    with pytest.raises(TranscriptionError):
        WhisperTranscriber._to_file(Path("nao/existe/audio.ogg"))


def test_transcribe_safe_devolve_vazio_em_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    transcriber = WhisperTranscriber()

    def _boom(*args, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("modelo indisponível")

    monkeypatch.setattr(transcriber, "_transcribe_path", _boom)
    sample = tmp_file = Path(__file__).parent / "_sample.wav"
    sample.write_bytes(b"RIFF0000WAVE")
    try:
        assert transcriber.transcribe_safe(sample) == ""
    finally:
        sample.unlink(missing_ok=True)


def test_transcribe_levanta_para_fonte_invalida() -> None:
    transcriber = WhisperTranscriber()
    with pytest.raises(TranscriptionError):
        transcriber.transcribe(Path("arquivo_que_nao_existe.ogg"))
