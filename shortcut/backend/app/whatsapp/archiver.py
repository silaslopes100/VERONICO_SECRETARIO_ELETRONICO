"""Arquivamento de conversas no WhatsApp Web (menu de contexto da sidebar)."""
from __future__ import annotations

import logging
from typing import Any

from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.inbox_reader import sanitize_text

logger = logging.getLogger(__name__)

_ARCHIVE_WORDS = ("arquivar conversa", "archive chat", "arquivar", "archive")


async def _click_archive_menu(page: Any) -> bool:
    items = page.locator('[role="menuitem"], [role="menuitem"] span')
    count = await items.count()
    for idx in range(count):
        item = items.nth(idx)
        try:
            label = (await item.inner_text(timeout=800)).strip().lower()
        except Exception:  # noqa: BLE001
            continue
        if any(word in label for word in _ARCHIVE_WORDS):
            await item.click(timeout=2500)
            return True
    return False


class Archiver:
    """Arquiva a conversa real no WhatsApp e devolve ``True`` em sucesso."""

    async def archive(self, chat_name: str) -> bool:
        name = sanitize_text(chat_name, 80)
        if not name:
            return False
        manager = get_browser_manager()
        if not manager.connected:
            raise RuntimeError("WhatsApp Web não conectado.")
        async with await manager.operation():
            page = await manager.get_page()
            row = page.locator(f'#pane-side [title="{name}"]')
            if await row.count() == 0:
                logger.error("Conversa não encontrada para arquivar: %s", name)
                return False
            try:
                await row.first.click(button="right", timeout=4000)
                await page.wait_for_timeout(500)
                archived = await _click_archive_menu(page)
            except Exception as exc:  # noqa: BLE001
                logger.error("Falha ao arquivar %s: %s", name, exc)
                archived = False
            finally:
                await page.keyboard.press("Escape")
        if archived:
            logger.info("Conversa arquivada: %s", name)
        return archived


_archiver: Archiver | None = None


def get_archiver() -> Archiver:
    global _archiver
    if _archiver is None:
        _archiver = Archiver()
    return _archiver
