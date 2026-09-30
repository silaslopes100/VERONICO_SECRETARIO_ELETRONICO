"""Leitura das conversas não lidas do WhatsApp Web.

A extração é feita em duas camadas para facilitar testes unitários:
1. ``EXTRACT_JS`` varre o DOM da sidebar e devolve dados brutos (dicts).
2. :func:`parse_rows` transforma os dados brutos em :class:`UnreadConversation`
   aplicando sanitização (anti-XSS) e validações — pura, sem navegador.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.whatsapp.browser_manager import get_browser_manager

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]*>")
_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")
MAX_TEXT = 400

# Varre a lista de conversas e devolve dados brutos por linha.
EXTRACT_JS = """
() => {
  const side = document.querySelector('#pane-side');
  if (!side) return [];
  const rows = side.querySelectorAll('[role="listitem"], div[role="row"]');
  const out = [];
  rows.forEach((row, idx) => {
    const titleEl =
      row.querySelector('[data-testid="cell-name-title"]') ||
      row.querySelector('span[title][dir="auto"]') ||
      row.querySelector('span[title]');
    const name = titleEl ? (titleEl.getAttribute('title') || titleEl.textContent || '') : '';
    const previewEl =
      row.querySelector('[data-testid="cell-body-text"]') ||
      row.querySelector('span[title][dir="auto"]:not(:first-child)');
    const preview = previewEl ? (previewEl.getAttribute('title') || previewEl.textContent || '') : '';
    const timeEl = row.querySelector('[data-testid="cell-meta"] span, span[aria-label]');
    const time = timeEl ? (timeEl.getAttribute('aria-label') || timeEl.textContent || '') : '';
    let badge = null;
    row.querySelectorAll('span, div').forEach((el) => {
      const label = (el.getAttribute('aria-label') || '').toLowerCase();
      const txt = (el.textContent || '').trim();
      const cls = (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) || '';
      if (/unread|n[aã]o lidas|não lidas/.test(label + ' ' + cls) ||
          (/^[0-9]{1,3}$/.test(txt) && /unread|badge|_1p0r5/.test(cls + ' ' + label))) {
        badge = el;
      }
    });
    const audio = row.querySelector('[data-testid="audio-play"], audio, [aria-label*="udio"], [aria-label*="Áudio"]') !== null;
    const holder = row.closest ? row.closest('[data-id]') : null;
    const dataId = row.getAttribute('data-id') || (holder ? holder.getAttribute('data-id') : '') || '';
    out.push({
      index: idx,
      dataId: String(dataId).trim(),
      hasUnread: badge !== null,
      name: name.trim(),
      preview: preview.trim(),
      time: time.trim(),
      unread: badge ? (parseInt((badge.textContent || '1').replace(/\\D/g, ''), 10) || 1) : 1,
      isAudio: audio,
      testid: row.getAttribute('data-testid') || '',
      text: (row.innerText || '').slice(0, 600)
    });
  });
  return out;
}
"""

# Observa a sidebar e notifica o backend (via binding) a cada mudança relevante.
# Idempotente: reanexa se o #pane-side for trocado por um reload da página.
ENSURE_OBSERVER_JS = """
() => {
  const side = document.querySelector('#pane-side');
  if (!side) return false;
  const existing = window.__shortcutObs;
  if (existing && window.__shortcutObsTarget === side && side.isConnected) return true;
  if (existing) { try { existing.disconnect(); } catch (e) {} }
  let timer = null;
  const notify = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      try { window.shortcutSidebarChanged(); } catch (e) {}
    }, 300);
  };
  const obs = new MutationObserver(notify);
  obs.observe(side, { childList: true, subtree: true, characterData: true });
  window.__shortcutObs = obs;
  window.__shortcutObsTarget = side;
  return true;
}
"""


def sanitize_text(value: str | None, max_len: int = MAX_TEXT) -> str:
    """Normaliza texto vindo do WhatsApp removendo riscos de XSS e ruído."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _BLOCK_RE.sub("", text)       # remove blocos <script>/<style> com conteúdo
    text = _TAG_RE.sub("", text)         # remove marcação HTML/JS
    text = _CTRL_RE.sub("", text)         # remove caracteres de controle
    text = text.replace("\u200b", "").replace("\u200e", "").replace("\u200f", "")
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _slugify(name: str) -> str:
    lowered = "".join(
        c for c in unicodedata.normalize("NFD", name.lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-") or "chat"


def make_chat_id(name: str, index: int) -> str:
    """Identificador legível de um card/conversa (slug + índice da linha)."""
    return f"{_slugify(name)}-{index}"


def stable_chat_id(name: str, index: int, data_id: str = "", *, duplicated: bool = False) -> str:
    """ID estável da conversa: JID do WhatsApp > slug do nome > slug + índice.

    A ordem da sidebar muda a cada mensagem recebida; usar o índice da linha
    como identidade faz o "mesmo" chat virar um chat novo (card duplicado) ou
    sumir. O ``data-id`` da linha é a identidade real do chat no WhatsApp.
    """
    data_id = sanitize_text(data_id, 120)
    if data_id:
        return f"jid:{data_id}"
    slug = _slugify(name)
    if duplicated:
        return f"{slug}-{index}"
    return slug


@dataclass
class UnreadConversation:
    """Representação de uma conversa não lida pronta para virar card Kanban."""

    chat_id: str
    name: str
    preview: str
    timestamp: str
    is_audio: bool = False
    unread_count: int = 1
    raw_text: str = ""
    detected_at: float = field(default_factory=time.time)

    @property
    def sanitized_preview(self) -> str:
        return sanitize_text(self.preview)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "name": sanitize_text(self.name, 80),
            "preview": sanitize_text(self.preview),
            "timestamp": sanitize_text(self.timestamp, 60),
            "is_audio": self.is_audio,
            "unread_count": self.unread_count,
            "detected_at": self.detected_at,
        }


def parse_rows(rows: list[dict[str, Any]], *, seen: set[str] | None = None) -> list[UnreadConversation]:
    """Converte linhas brutas do DOM em conversas (pura — usada nos testes).

    Filtra conversas lidas quando o lote trouxe ao menos um badge de não-lida.
    Válvula de segurança: se nenhum badge foi detectado (seletor do WhatsApp
    mudou), não filtra nada — melhor arriscar cards extras que ficar mudo.
    """
    seen = seen if seen is not None else set()
    names = [sanitize_text(row.get("name"), 80) for row in rows]
    any_unread = any(bool(row.get("hasUnread")) for row in rows)
    candidates = [
        (row, name)
        for row, name in zip(rows, names)
        if name and not (any_unread and not row.get("hasUnread"))
    ]
    name_counts: dict[str, int] = {}
    for _, name in candidates:
        name_counts[name] = name_counts.get(name, 0) + 1
    conversations: list[UnreadConversation] = []
    for row, name in candidates:
        preview = sanitize_text(row.get("preview") or row.get("text"), MAX_TEXT)
        chat_id = stable_chat_id(
            name,
            int(row.get("index", 0)),
            str(row.get("dataId") or ""),
            duplicated=name_counts[name] > 1,
        )
        if chat_id in seen:
            continue
        seen.add(chat_id)
        conversations.append(
            UnreadConversation(
                chat_id=chat_id,
                name=name,
                preview=preview or "(sem texto — possível áudio)",
                timestamp=sanitize_text(row.get("time"), 60),
                is_audio=bool(row.get("isAudio")),
                unread_count=max(1, int(row.get("unread") or 1)),
                raw_text=sanitize_text(row.get("text"), 600),
            )
        )
    return conversations


async def open_chat(page: Any, chat_name: str) -> bool:
    """Abre a conversa pelo nome (sidebar) e devolve ``True`` se encontrada."""
    name = sanitize_text(chat_name, 80)
    if not name:
        return False
    # 1) Tenta clicar direto na célula com o título igual.
    cell = page.locator(f'#pane-side [title="{name}"]')
    try:
        if await cell.count() > 0:
            await cell.first.click(timeout=4000)
            await page.wait_for_timeout(400)
            return True
    except Exception:  # noqa: BLE001 - cai para a busca
        logger.debug("Clique direto falhou para %s; usando busca", name)
    # 2) Busca global do contato.
    try:
        search = page.locator('[data-testid="chat-list-search"], #side [contenteditable="true"]').first
        await search.click(timeout=3000)
        await search.fill(name)
        await page.wait_for_timeout(700)
        result = page.locator(f'#pane-side [title="{name}"]')
        if await result.count() == 0:
            result = page.locator('#pane-side div[role="listitem"]').first
        await result.click(timeout=4000)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível abrir a conversa %r: %s", name, exc)
        return False


class InboxReader:
    """Lê conversas não lidas na página viva do WhatsApp Web."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._known: dict[str, UnreadConversation] = {}

    async def read_unread(self, seen: set[str] | None = None) -> list[UnreadConversation]:
        """Coleta as conversas visíveis na sidebar (não-lidas, com válvula de segurança)."""
        manager = get_browser_manager()
        if not manager.connected:
            return []
        async with await manager.operation():
            page = await manager.get_page()
            try:
                await page.evaluate(ENSURE_OBSERVER_JS)
            except Exception:  # noqa: BLE001 - página pode estar recarregando
                logger.debug("Não foi possível instalar o observer da sidebar", exc_info=True)
            try:
                raw_rows = await page.evaluate(EXTRACT_JS)
            except Exception as exc:  # noqa: BLE001 - página pode recarregar
                logger.warning("Falha ao ler sidebar: %s", exc)
                return []
        conversations = parse_rows(raw_rows or [], seen=seen if seen is not None else self._seen)
        for conv in conversations:
            self._known[conv.chat_id] = conv
        if conversations:
            logger.info("%d conversa(s) detectada(s)", len(conversations))
        return conversations

    # ------------------------------------------------------------------ polling
    async def poll_once(self) -> list[Any]:
        """Lê a caixa, cria/atualiza cards e transcreve áudios recebidos.

        Conversa que já tem card é atualizada (preview, contagem e reabertura
        em "Nova mensagem"); só sem card correspondente um é criado.
        Retorna apenas os cards criados neste passeio.
        """
        from app.kanban.models import Conversation
        from app.kanban.state_manager import get_state_manager

        state = get_state_manager()
        known_ids = set(state.cards.keys())
        conversations = await self.read_unread(seen=set())
        created: list[Any] = []
        touched = 0
        for conv in conversations:
            conversation = Conversation(
                chat_id=conv.chat_id,
                name=conv.name,
                preview=conv.preview,
                timestamp=conv.timestamp,
                is_audio=conv.is_audio,
                unread_count=conv.unread_count,
            )
            card = await state.update_conversation(conversation)
            if card is None:
                card = await state.add_conversation(conversation)
            if card is None:
                continue
            touched += 1
            if card.id not in known_ids:
                created.append(card)
            if conv.is_audio and not card.transcript:
                await self._transcribe_audio(card)
        if touched:
            logger.info("%d conversa(s) processada(s); %d card(s) novo(s)", touched, len(created))
        return created

    async def _transcribe_audio(self, card: Any) -> None:
        """Baixa o áudio da conversa e grava a transcrição no card."""
        from app.audio.whisper_transcriber import get_transcriber
        from app.kanban.state_manager import get_state_manager
        from app.whatsapp.audio_extractor import get_audio_extractor

        try:
            path = await get_audio_extractor().download_latest(card.contact)
            if not path:
                return
            text = await asyncio.to_thread(
                get_transcriber().transcribe_safe, path, language="pt"
            )
            if text:
                await get_state_manager().set_transcript(card.id, text)
                logger.info("Áudio de %s transcrito.", card.contact)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transcrição de %s falhou: %s", card.contact, exc)

    def get(self, chat_id: str) -> UnreadConversation | None:
        return self._known.get(chat_id)

    async def wait_connected(self, timeout: float = 120.0) -> bool:
        """Aguarda o login (QR escaneado) por até ``timeout`` segundos."""
        manager = get_browser_manager()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if manager.connected:
                return True
            await asyncio.sleep(1)
        return False


_polling_task: asyncio.Task | None = None
_refresh_task: asyncio.Task | None = None
_refresh_queued = False
_last_disconnected_log = 0.0


def schedule_sidebar_refresh(delay: float = 0.4) -> None:
    """Agenda um poll imediato — chamado pelo MutationObserver via binding.

    Coalesce de rajadas: se já existe um refresh em andamento, marca "sujo"
    e repete o passeio depois dele, sem empilhar polls concorrentes.
    """
    global _refresh_task, _refresh_queued
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # sem event loop (inicialização síncrona)
        return
    if _refresh_task is not None and not _refresh_task.done():
        _refresh_queued = True
        return

    async def _run() -> None:
        global _refresh_task, _refresh_queued
        try:
            while True:
                await asyncio.sleep(delay)
                try:
                    await get_inbox_reader().poll_once()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Poll agendado pelo observer falhou: %s", exc)
                if not _refresh_queued:
                    break
                _refresh_queued = False
        finally:
            _refresh_task = None

    _refresh_task = loop.create_task(_run(), name="sidebar-refresh")


async def _polling_loop() -> None:
    from app.config import get_settings

    global _last_disconnected_log
    reader = get_inbox_reader()
    interval = get_settings().poll_interval_seconds
    while True:
        try:
            if get_browser_manager().connected:
                _last_disconnected_log = 0.0
                await reader.poll_once()
            elif time.monotonic() - _last_disconnected_log > 60:
                _last_disconnected_log = time.monotonic()
                logger.warning("Polling pulado: WhatsApp Web não está conectado.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - o loop nunca pode morrer
            logger.warning("Erro no polling da caixa de entrada: %s", exc)
        await asyncio.sleep(interval)


def start_inbox_polling() -> asyncio.Task:
    """Inicia o loop de leitura periódica (chamado no startup do backend)."""
    global _polling_task
    if _polling_task is None or _polling_task.done():
        _polling_task = asyncio.create_task(_polling_loop(), name="inbox-polling")
        logger.info("Polling da caixa de entrada iniciado.")
    return _polling_task


def stop_inbox_polling() -> None:
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
    _polling_task = None


_reader: InboxReader | None = None


def get_inbox_reader() -> InboxReader:
    global _reader
    if _reader is None:
        _reader = InboxReader()
    return _reader
