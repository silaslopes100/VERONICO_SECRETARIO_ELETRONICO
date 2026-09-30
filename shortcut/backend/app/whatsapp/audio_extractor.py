"""Download/isolamento de áudios das mensagens de voz do WhatsApp Web.

Estratégia: a conversa é aberta, o elemento de áudio é disparado (play) e a
resposta de rede com ``content-type`` de áudio é interceptada e salva em disco
(``shortcut_data/audio/``) para depois ser transcrita pelo Whisper.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.inbox_reader import open_chat

logger = logging.getLogger(__name__)

AUDIO_SELECTOR = '[data-testid="audio-play"]'
_AUDIO_TYPES = ("audio", "ogg", "opus", "mpeg", "mp4a", "webm")


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")[:60] or "audio"


class AudioExtractor:
    """Coleta arquivos de áudio recebidos no WhatsApp."""

    def __init__(self, output_dir: Path | None = None) -> None:
        settings = get_settings()
        self.output_dir = output_dir or (settings.data_dir / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, payload: bytes, origin: str = "chat") -> Path:
        """Grava bytes de áudio em disco com nome único."""
        ext = ".ogg" if payload[:4] == b"OggS" else ".opus" if payload[:4] == b"RIFF" else ".ogg"
        path = self.output_dir / f"{_safe_name(origin)}_{int(time.time() * 1000)}{ext}"
        path.write_bytes(payload)
        logger.info("Áudio salvo em %s (%d bytes)", path.name, len(payload))
        return path

    async def download_from_chat(self, chat_name: str, limit: int = 1) -> list[Path]:
        """Abre a conversa, dispara o play dos áudios e captura os arquivos."""
        manager = get_browser_manager()
        if not manager.connected:
            logger.warning("WhatsApp não conectado; download de áudio cancelado.")
            return []
        async with await manager.operation():
            page = await manager.get_page()
            if not await open_chat(page, chat_name):
                return []
            return await self._capture_on_page(page, chat_name, limit)

    async def _capture_on_page(self, page: Any, chat_name: str, limit: int) -> list[Path]:
        sounds: list[bytes] = []
        done = {"flag": False}

        async def on_response(response) -> None:  # noqa: ANN001 - tipo do Playwright
            try:
                ctype = (response.headers or {}).get("content-type", "").lower()
                if any(t in ctype for t in _AUDIO_TYPES) and "json" not in ctype:
                    body = await response.body()  # body() é assíncrono no Playwright
                    if body and len(body) > 512:
                        sounds.append(body)
            except Exception:  # noqa: BLE001 - respostas descartadas são comuns
                pass

        page.on("response", on_response)
        try:
            players = page.locator(AUDIO_SELECTOR)
            count = min(await players.count(), limit)
            for idx in range(count):
                try:
                    await players.nth(idx).click(timeout=3000)
                    await page.wait_for_timeout(1500)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Não foi possível tocar áudio %d: %s", idx, exc)
                if len(sounds) >= count:
                    break
        finally:
            page.remove_listener("response", on_response)

        paths = [self.save(chunk, chat_name) for chunk in sounds[:limit]]
        done["flag"] = bool(paths)
        return paths

    async def download_latest(self, chat_name: str) -> Path | None:
        """Conveniência: devolve o áudio mais recente da conversa."""
        paths = await self.download_from_chat(chat_name, limit=1)
        return paths[0] if paths else None


_extractor: AudioExtractor | None = None


def get_audio_extractor() -> AudioExtractor:
    global _extractor
    if _extractor is None:
        _extractor = AudioExtractor()
    return _extractor
