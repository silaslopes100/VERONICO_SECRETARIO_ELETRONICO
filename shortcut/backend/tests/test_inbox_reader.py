"""Testes da leitura da caixa de entrada (funções puras)."""
from __future__ import annotations

import asyncio

from app.whatsapp import inbox_reader as inbox_reader_module
from app.whatsapp.inbox_reader import (
    make_chat_id,
    parse_rows,
    sanitize_text,
    schedule_sidebar_refresh,
    stable_chat_id,
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
        assert conv.chat_id == "maria"

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

    def test_id_estavel_quando_sidebar_reordena(self) -> None:
        """O índice da linha muda a cada mensagem — o chat_id NÃO pode mudar."""
        first = parse_rows([self._row(index=0)])
        second = parse_rows([self._row(index=7)])
        assert first[0].chat_id == second[0].chat_id

    def test_prefere_jid_quando_presente(self) -> None:
        conv = parse_rows([self._row(dataId="5511999999999@c.us")])[0]
        assert conv.chat_id == "jid:5511999999999@c.us"
        other = parse_rows([self._row(index=9, dataId="5511999999999@c.us")])[0]
        assert other.chat_id == conv.chat_id

    def test_nome_duplicado_usa_indice(self) -> None:
        rows = [self._row(index=0), self._row(index=3)]
        conversations = parse_rows(rows)
        assert {c.chat_id for c in conversations} == {"maria-0", "maria-3"}

    def test_filtra_lidas_quando_ha_badge_no_lote(self) -> None:
        rows = [
            self._row(name="Ana", hasUnread=True),
            self._row(index=1, name="Bruno", hasUnread=False),
        ]
        conversations = parse_rows(rows)
        assert [c.name for c in conversations] == ["Ana"]

    def test_valvula_sem_badge_nao_filtra_nada(self) -> None:
        """Se nenhum badge foi detectado (seletor quebrou), aceita tudo."""
        rows = [self._row(name="Ana"), self._row(index=1, name="Bruno")]
        assert len(parse_rows(rows)) == 2


class TestStableChatId:
    def test_jid_tem_prioridade(self) -> None:
        assert stable_chat_id("Maria", 4, "123@c.us") == "jid:123@c.us"

    def test_fallback_nome_sem_indice(self) -> None:
        assert stable_chat_id("João & Maria", 4) == "joao-maria"

    def test_duplicado_recebe_indice(self) -> None:
        assert stable_chat_id("Maria", 4, duplicated=True) == "maria-4"


class TestScheduleSidebarRefresh:
    async def test_coalesce_de_rajadas(self, monkeypatch) -> None:
        calls: list[int] = []

        async def fake_poll(self) -> list:
            calls.append(1)
            return []

        monkeypatch.setattr(inbox_reader_module.InboxReader, "poll_once", fake_poll)
        inbox_reader_module._refresh_queued = False
        schedule_sidebar_refresh(delay=0.01)
        schedule_sidebar_refresh(delay=0.01)
        for _ in range(100):
            if inbox_reader_module._refresh_task is None:
                break
            await asyncio.sleep(0.01)
        assert inbox_reader_module._refresh_task is None
        assert len(calls) == 2  # 1º passeio + 1 repasseio (sujo), sem empilhar


class TestMakeChatId:
    def test_slug_estavel(self) -> None:
        assert make_chat_id("João & Maria", 3) == "joao-maria-3"

    def test_nome_vazio_usaFallback(self) -> None:
        assert make_chat_id("", 1) == "chat-1"
