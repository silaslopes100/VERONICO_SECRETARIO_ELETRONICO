"""Gerencia a sessão persistente do Playwright/Chromium para o WhatsApp Web.

Responsabilidades:
- subir/derrubar o navegador controlado (Chromium com ``user-data-dir``);
- manter a página ``https://web.whatsapp.com/`` viva e detectar login (QR);
- expor um lock de operações para que leitura/envio não colidam;
- publicar mudanças de status (``starting``/``waiting_qr``/``connected``/``error``).
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class WhatsAppStatus(str, Enum):
    STARTING = "starting"
    WAITING_QR = "waiting_qr"
    CONNECTED = "connected"
    ERROR = "error"
    STOPPED = "stopped"


class BrowserManager:
    """Singleton que mantém o Chromium vivo durante todo o ciclo do backend."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._playwright = None
        self._context = None
        self._page = None
        self._status = WhatsAppStatus.STOPPED
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------------ status
    @property
    def status(self) -> WhatsAppStatus:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self._status.value,
            "last_error": self._last_error,
            "headless": self.settings.headless,
        }

    def _set_status(self, status: WhatsAppStatus, error: str | None = None) -> None:
        if status == self._status and error == self._last_error:
            return
        self._status = status
        self._last_error = error
        from app.api.ws_gateway import publish  # import tardio evita ciclo

        publish({"type": "whatsapp_status", "payload": self.snapshot()})

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Inicia Playwright + Chromium e abre o WhatsApp Web."""
        if self._task and not self._task.done():
            return
        self._set_status(WhatsAppStatus.STARTING)
        self._task = asyncio.create_task(self._run(), name="whatsapp-browser")

    async def _run(self) -> None:
        try:
            from playwright.async_api import async_playwright

            self.settings.whatsapp_user_data_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.whatsapp_user_data_dir),
                headless=self.settings.headless,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            await self._page.goto(self.settings.whatsapp_url, wait_until="domcontentloaded")
            logger.info("Chromium iniciado; sessão em %s", self.settings.whatsapp_user_data_dir)
            await self._watch_login()
        except asyncio.CancelledError:  # noqa: PERF203
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao iniciar o navegador do WhatsApp")
            self._set_status(WhatsAppStatus.ERROR, str(exc))

    async def _watch_login(self) -> None:
        """Aguarda a tela principal do WhatsApp (QR escaneado ou sessão salva)."""
        assert self._page is not None
        while True:
            try:
                qr = await self._page.locator('canvas[aria-label], div[data-ref]').count()
                logged = await self._page.locator('#pane-side').count()
            except Exception:  # página recarregou
                await asyncio.sleep(1)
                continue
            if logged > 0:
                self._set_status(WhatsAppStatus.CONNECTED)
                return
            if qr > 0:
                self._set_status(WhatsAppStatus.WAITING_QR)
            await asyncio.sleep(2)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        for closer in (self._context, self._playwright):
            if closer is None:
                continue
            try:
                await closer.close()
            except Exception:  # noqa: BLE001
                pass
        self._context = None
        self._playwright = None
        self._page = None
        self._set_status(WhatsAppStatus.STOPPED)

    # ------------------------------------------------------------------ access
    @property
    def connected(self) -> bool:
        return self._status is WhatsAppStatus.CONNECTED

    async def get_page(self):
        """Devolve a página ativa, validando que o WhatsApp está logado."""
        if not self.connected or self._page is None:
            raise RuntimeError("WhatsApp Web não conectado (aguardando QR Code).")
        return self._page

    async def operation(self):
        """Context manager serializando operações de automação na página."""
        return self._lock


_manager: BrowserManager | None = None


def get_browser_manager() -> BrowserManager:
    """Singleton do gerenciador de navegador."""
    global _manager
    if _manager is None:
        _manager = BrowserManager()
    return _manager
