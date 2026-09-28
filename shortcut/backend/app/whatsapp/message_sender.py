"""Envio de mensagens de texto para conversas do WhatsApp Web."""
from __future__ import annotations

import logging
from typing import Any

from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.inbox_reader import open_chat, sanitize_text

logger = logging.getLogger(__name__)

COMPOSER = '#footer [contenteditable="true"], [data-testid="conversation-compose-box-input"]'
SEND_KEYS = "Enter"


async def _type_and_send(page: Any, text: str) -> bool:
    composer = page.locator(COMPOSER).first
    await composer.wait_for(state="visible", timeout=6000)
    await composer.click()
    await page.keyboard.type(text, delay=12)
    await page.wait_for_timeout(200)
    await page.keyboard.press(SEND_KEYS)
    await page.wait_for_timeout(500)
    return True


class MessageSender:
    """Responsável único por inserir texto no campo e disparar o envio."""

    async def send_text(self, chat_name: str, text: str) -> bool:
        """Envia ``text`` como resposta na conversa ``chat_name``."""
        clean = sanitize_text(text, 4000)
        if not clean:
            logger.warning("Envio cancelado: texto vazio após sanitização.")
            return False
        manager = get_browser_manager()
        if not manager.connected:
            raise RuntimeError("WhatsApp Web não conectado.")
        async with await manager.operation():
            page = await manager.get_page()
            if not await open_chat(page, chat_name):
                logger.error("Conversa não encontrada: %s", chat_name)
                return False
            sent = await _type_and_send(page, clean)
        if sent:
            logger.info("Mensagem enviada para %s", chat_name)
        return sent


_sender: MessageSender | None = None


def get_message_sender() -> MessageSender:
    global _sender
    if _sender is None:
        _sender = MessageSender()
    return _sender
