"""Testes do envio de mensagens (sanitização + interação com página falsa)."""
from __future__ import annotations

import pytest

from app.whatsapp.message_sender import MessageSender, _type_and_send


class FakeLocator:
    def __init__(self, page: "FakePage") -> None:
        self._page = page

    @property
    def first(self) -> "FakeLocator":
        return self

    async def wait_for(self, **kwargs) -> None:  # noqa: ANN003
        return None

    async def click(self, **kwargs) -> None:  # noqa: ANN003
        self._page.clicked = True


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self._page = page

    async def type(self, text: str, delay: int = 0) -> None:
        self._page.typed.append(text)

    async def press(self, key: str) -> None:
        self._page.pressed.append(key)


class FakePage:
    def __init__(self) -> None:
        self.typed: list[str] = []
        self.pressed: list[str] = []
        self.clicked = False
        self.keyboard = FakeKeyboard(self)

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self)

    async def wait_for_timeout(self, ms: int) -> None:
        return None


@pytest.mark.asyncio
async def test_type_and_send_escreve_e_envia() -> None:
    page = FakePage()
    assert await _type_and_send(page, "Olá, tudo bem?") is True
    assert page.typed == ["Olá, tudo bem?"]
    assert page.pressed == ["Enter"]
    assert page.clicked is True


@pytest.mark.asyncio
async def test_send_text_recusa_texto_vazio() -> None:
    sender = MessageSender()
    # Texto vazio/malicioso é descartado antes de tocar no navegador.
    assert await sender.send_text("Maria", "   ") is False
    assert await sender.send_text("Maria", "<script>alert(1)</script>") is False
