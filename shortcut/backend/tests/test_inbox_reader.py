"""Testes da leitura da caixa de entrada (funções puras)."""
from __future__ import annotations

from app.whatsapp.inbox_reader import (
    make_chat_id,
    parse_rows,
    sanitize_text,
)


class TestSanitizeText:
    def test_remove_html_tags(self) -> None:
        assert sanitize_text("<img src=x onerror=alert(1)>Olá") == "Olá"

    def test_escapa_entidades_e_remove_controle(self) -> None:
        assert sanitize_text("Bom&#10;dia\x00\x07!") == "Bom dia!"

    def test_colapsa_espacos(self) -> None:
        assert sanitize_text("  muitos   \n espaços  ") == "muitos espaços"

    def test_limita_tamanho(self) -> None:
        long = "x" * 1000
        out = sanitize_text(long, max_len=50)
        assert len(out) == 50
        assert out.endswith("…")

    def test_none_vira_vazio(self) -> None:
        assert sanitize_text(None) == ""


class TestParseRows:
    def _row(self, **overrides) -> dict:
        row = {
            "index": 0,
            "name": "Maria",
            "preview": "Bom dia!",
            "time": "09:12",
            "unread": 2,
            "isAudio": False,
            "text": "Maria: Bom dia!",
        }
        row.update(overrides)
        return row

    def test_converte_para_conversas(self) -> None:
        conversations = parse_rows([self._row()])
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv.name == "Maria"
        assert conv.preview == "Bom dia!"
        assert conv.unread_count == 2
        assert conv.chat_id == "maria-0"

    def test_pula_linhas_sem_nome(self) -> None:
        assert parse_rows([self._row(name="   ")]) == []

    def test_dedupe_por_chat_id(self) -> None:
        seen: set[str] = set()
        first = parse_rows([self._row()], seen=seen)
        second = parse_rows([self._row()], seen=seen)
        assert len(first) == 1
        assert second == []

    def test_marcador_de_audio_e_preview_alternativo(self) -> None:
        conv = parse_rows([self._row(preview="", text="🎤 mensagem de voz", isAudio=True)])[0]
        assert conv.is_audio is True
        assert conv.preview  # fallback aplicado

    def test_sanitiza_nome_malicioso(self) -> None:
        conv = parse_rows([self._row(name="<b>Hacker</b>")])[0]
        assert conv.name == "Hacker"


class TestMakeChatId:
    def test_slug_estavel(self) -> None:
        assert make_chat_id("João & Maria", 3) == "joao-maria-3"

    def test_nome_vazio_usaFallback(self) -> None:
        assert make_chat_id("", 1) == "chat-1"
