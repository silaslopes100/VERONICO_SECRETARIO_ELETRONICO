"""Cliente opcional da OpenRouter API (melhorias de transcrição/resumo).

Desligado por padrão (``OPENROUTER_ENABLED=false``). Quando ativo, pode:
- resumir mensagens longas para o preview do card;
- sugerir respostas ao usuário.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 30.0


class OpenRouterDisabled(RuntimeError):
    """Levantado quando a integração está desativada no .env."""


class OpenRouterClient:
    """Fachada enxuta sobre o endpoint de chat da OpenRouter."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.openrouter_enabled and self.settings.openrouter_api_key
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "Shortcut",
        }

    async def _chat(self, prompt: str, *, system: str) -> str:
        if not self.enabled:
            raise OpenRouterDisabled("OpenRouter desativado (OPENROUTER_ENABLED=false).")
        payload: dict[str, Any] = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "temperature": 0.3,
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(API_URL, json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    async def summarize(self, text: str, limit: int = 140) -> str:
        """Resumo curto da mensagem para o preview do card."""
        try:
            return await self._chat(
                text[:4000],
                system=f"Resuma em no máximo {limit} caracteres, em português, sem aspas.",
            )
        except Exception as exc:  # noqa: BLE001 - recurso opcional nunca derruba o fluxo
            logger.debug("Resumo indisponível: %s", exc)
            return text[:limit]

    async def suggest_reply(self, incoming: str) -> str:
        """Sugestão de resposta para a mensagem recebida."""
        try:
            return await self._chat(
                incoming[:4000],
                system=(
                    "Você é um assistente de mensagens. Sugira uma resposta curta, "
                    "educada e natural em português do Brasil. Apenas o texto da resposta."
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Sugestão indisponível: %s", exc)
            return ""


_client: OpenRouterClient | None = None


def get_openrouter_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client
