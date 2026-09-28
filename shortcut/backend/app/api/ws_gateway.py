"""WebSocket em tempo real: envia eventos de estado ao frontend.

``publish`` é o único ponto de entrada para qualquer módulo notificar o UI.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSConnectionManager:
    """Mantém o conjunto de conexões ativas e faz broadcast seguro."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        logger.info("WS conectado (%d ativo(s))", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        logger.info("WS desconectado (%d ativo(s))", len(self._clients))

    async def send(self, websocket: WebSocket, event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:  # noqa: BLE001
            await self.disconnect(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        for client in clients:
            await self.send(client, event)

    @property
    def count(self) -> int:
        return len(self._clients)


manager = WSConnectionManager()


def publish(event: dict[str, Any]) -> None:
    """Publica um evento para todos os clientes (thread-safe, best-effort)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # sem event loop ativo (ex.: inicialização síncrona)
    asyncio.ensure_future(manager.broadcast(event))


async def ws_endpoint(websocket: WebSocket) -> None:
    """Endpoint ``/ws``: envia o estado atual e mantém o canal aberto."""
    from app.kanban.state_manager import get_state_manager
    from app.whatsapp.browser_manager import get_browser_manager

    await manager.connect(websocket)
    await manager.send(websocket, {"type": "kanban_state", "payload": get_state_manager().snapshot()})
    await manager.send(websocket, {"type": "whatsapp_status", "payload": get_browser_manager().snapshot()})
    try:
        while True:
            # O cliente não precisa enviar nada; manter vivo com ping/pong.
            await websocket.receive_text()
    except Exception:  # noqa: BLE001 - desconexão normal
        pass
    finally:
        await manager.disconnect(websocket)
