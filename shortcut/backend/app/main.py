"""Criação do app FastAPI: rotas, middleware e ciclo de vida.

Sem lógica de negócio aqui — apenas composição/orquestração dos módulos.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.rate_limit import RateLimitMiddleware, RateLimiter
from app.api.routes_cards import router as cards_router
from app.api.routes_voice import router as voice_router
from app.api.ws_gateway import ws_endpoint
from app.config import get_settings
from app.whatsapp.browser_manager import get_browser_manager
from app.whatsapp.inbox_reader import start_inbox_polling, stop_inbox_polling
from app.whatsapp.session_store import get_session_store


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """Sobe navegador + polling na inicialização e encerra no desligamento."""
    settings = get_settings()
    get_session_store().ensure()
    await get_browser_manager().start()
    start_inbox_polling()
    yield
    stop_inbox_polling()
    await get_browser_manager().stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Shortcut",
        description="Secretária eletrônica pessoal para WhatsApp Web.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds),
    )
    app.include_router(cards_router)
    app.include_router(voice_router)
    app.add_api_websocket_route("/ws", ws_endpoint)
    return app


app = create_app()
