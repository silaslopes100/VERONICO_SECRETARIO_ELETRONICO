# Shortcut — Arquitetura

## 1. Visão geral

O Shortcut é um sistema local (24/7 em `localhost`) composto por dois processos:

```
┌──────────────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (Vite + React, :5173)      │  REST  │  Backend (FastAPI, :8000)            │
│  ─ Home (status + acesso)            │◄──────►│  ─ routes_cards / routes_voice       │
│  ─ Dashboard (Kanban MSN)            │  WS    │  ─ ws_gateway (eventos tempo real)   │
│  ─ hooks (WS, mic, estado Kanban)    │◄──────►│  ─ kanban (models/state/orchestrator)│
└──────────────────────────────────────┘        │  ─ audio (whisper/mic/TTS)           │
                                                │  ─ whatsapp (Playwright/Chromium)    │
                                                │  ─ openrouter (IA opcional)          │
                                                └───────────────┬──────────────────────┘
                                                                │ Playwright (CDP)
                                                ┌───────────────▼──────────────────────┐
                                                │  Chromium persistente (user-data-dir)│
                                                │  https://web.whatsapp.com/           │
                                                └──────────────────────────────────────┘
```

Regra de organização: **`main.py` e `App.tsx` não contêm lógica de negócio** — apenas
registram rotas/middleware e alternam telas. Cada responsabilidade vive no seu módulo.

---

## 2. Ciclo de vida do backend

1. `run_backend.py` → `uvicorn app.main:app`.
2. **lifespan** (`app/main.py`):
   - `session_store.ensure()` cria o diretório de perfil;
   - `browser_manager.start()` sobe Chromium persistente e abre o WhatsApp Web;
   - `inbox_reader.start_inbox_polling()` inicia o loop de leitura (`POLL_INTERVAL_SECONDS`).
3. `browser_manager` observa a página:
   - QR visível → status `waiting_qr` (publicado por WebSocket);
   - `#pane-side` presente → status `connected`.
4. No shutdown: polling cancelado, navegador fechado.

---

## 3. Fluxo do Kanban

### 3.1 Colunas e transições

```
Nova mensagem ──▶ Ouvidas ──▶ Aguardando resposta ──▶ Respondidas
     │               │               │                    │
     │ (avanço       │               │                    │ (arquivar no
     └──────────────▶└──────────────▶│◀───────────────────┘   WhatsApp e
                        (volta 1 passo permitida)             remove o card)
```

As transições válidas estão em `kanban/state_manager.py → ALLOWED_TRANSITIONS`;
qualquer outra combinação retorna **409 Conflict** na API.

### 3.2 Chegada de mensagens (push + pull)

```
MutationObserver (#pane-side) → binding "shortcutSidebarChanged"
   └─ schedule_sidebar_refresh() → poll imediato (~0,7 s)
polling loop (inbox_reader, fallback a cada POLL_INTERVAL_SECONDS)
   └─ read_unread()  → EXTRACT_JS varre a sidebar → parse_rows() sanitiza
        ├─ state_manager.add_conversation()      → card novo em "Nova mensagem"
        └─ state_manager.update_conversation()   → card existente atualizado;
             (preview/badge mudaram → reabre em "Nova mensagem")
             └─ se is_audio sem transcrição: audio_extractor.download_latest()
                              → whisper_transcriber.transcribe()
                              → state_manager.set_transcript()
        └─ publica evento "kanban_state" (WebSocket) → UI atualiza + toca som MSN
```

Identidade do chat: `data-id` (JID) da linha da sidebar → estável entre
reordenações; fallback para o slug do nome. Cards antigos (slug + índice) são
adotados pelo nome no primeiro poll (migração automática). Conversas lidas só
entram se o lote trouxer ao menos um badge de não-lida (válvula: se nenhum
badge for detectado, nada é filtrado).

### 3.3 Interações do card

| Botão | Caminho |
| --- | --- |
| **▶ Play** | Frontend lê `transcript || preview` com `speechSynthesis` (pt-BR) **e** dispara `POST /api/voice/speak` (TTS do servidor, pyttsx3). |
| **🎤 Responder** | `useVoiceRecorder` grava 5 s no navegador → `POST /api/voice/transcribe` (Whisper) → `POST /api/cards/{id}/reply-text` → Playwright digita no campo e envia → card `Ouvidas → Aguardando resposta → Respondidas`. |
| **◀ ▶ mover** | `POST /api/cards/{id}/move` (valida transição) → evento WS. |
| **📦 Arquivar** (só em *Respondidas*) | `POST /api/cards/{id}/archive` → menu de contexto do WhatsApp → card removido do quadro. |

---

## 4. Fluxo de voz (esteira)

### 4.1 Botão "Você tem X mensagens não lidas"

1. `POST /api/voice/announce` → TTS fala:
   *“Você tem X mensagens não lidas. Deseja ouvi-las agora?”*
2. `voice_command_listener` grava 5 s do microfone (sounddevice) → Whisper.
3. `classify_command()`:
   - **sim / pode ser / vamos lá** → `flow_orchestrator.start()`;
   - qualquer outra → responde com o comando não reconhecido (nada é lido).

### 4.2 Esteira (um card por vez, na ordem das colunas)

```
_run():
  pega próximo card ainda não processado (coluna "Nova mensagem" → "Ouvidas")
  1. garante transcrição (baixa/transcreve áudio, se for o caso)
  2. TTS: "Mensagem de {contato}. {transcrição}"
  3. card "Nova mensagem" → "Ouvidas"
  4. escuta comando de voz (timeout 5 s):
       "responder" → grava resposta (10 s) → envia no WhatsApp
                    → "Ouvidas" → "Aguardando resposta" → (envio confirmado) → "Respondidas"
       "próxima"   → passa ao próximo card
       "arquivar"  → arquiva a conversa e remove o card
       "não/parar" → encerra a esteira
       silêncio    → avança automaticamente (comportamento de esteira)
  5. volta ao passo 1 com o próximo card da fila
```

Comandos reconhecidos (normalizados sem acento, em `kanban/flow_orchestrator.py`):

| Comando | Variações aceitas |
| --- | --- |
| Confirmar | sim, yes, isso, pode ser, vamos la, confirma, claro |
| Próxima | próxima/proximo, pula, next, seguir, continua |
| Responder | responder, responda, resposta, falar, contestar |
| Arquivar | arquivar, arquiva, archive |
| Parar | não/no, para, cancela, cancelar, parar, stop |

O estado do fluxo é publicado como evento `flow_status` (card atual, último comando).

---

## 5. Tempo real (WebSocket)

`GET /ws` → ao conectar o cliente recebe `kanban_state` + `whatsapp_status` e depois
apenas eventos de mudança:

| Evento | Origem |
| --- | --- |
| `kanban_state` | `state_manager` (toda mutação: criar/atualizar/reabrir/mover/transcrever/arquivar) |
| `whatsapp_status` | `browser_manager` (starting / waiting_qr / connected / error) |
| `flow_status` | `flow_orchestrator` (esteira ativa, card atual) |

O frontend (`useWebSocket`) reconecta em backoff de 1 s → 10 s e, como
fallback, faz `GET /api/state` a cada 10 s — a UI nunca fica congelada sem F5.

---

## 6. Áudio

| Direção | Módulo | Caminho |
| --- | --- | --- |
| Recebido (WhatsApp → texto) | `audio_extractor` + `whisper_transcriber` | clique no player + interceptação da resposta `content-type: audio/*` → `.ogg` em `shortcut_data/audio/` → faster-whisper |
| Enviado (voz → WhatsApp) | `useVoiceRecorder` (navegador) → `routes_voice.transcribe` | `MediaRecorder` → WAV/WEBM → Whisper → `message_sender` |
| Comandos de voz | `voice_command_listener` | sounddevice (16 kHz mono, ≤ `AUDIO_MAX_SECONDS`) → Whisper |
| Leitura | `tts_speaker` (servidor, pyttsx3) e `speechSynthesis` (navegador) | fila única de fala, texto sanitizado (`clean_for_speech`) |

---

## 7. Segurança

- **Segredos**: `.env` claro ou `.env.enc` (Fernet). A chave mestra vem **apenas** de
  `SHORTCUT_MASTER_KEY` no ambiente do SO; `secrets_loader` decifra em memória no boot
  e nunca grava o texto puro em disco.
- **Sanitização**: todo texto do WhatsApp passa por `inbox_reader.sanitize_text`
  (remove blocos `<script>/<style>`, tags, caracteres de controle, normaliza espaços,
  limita tamanho) antes de chegar ao estado exibido.
- **XSS no frontend**: React escapa por padrão; o backend já entrega texto limpo.
- **Rate limiting**: `api/rate_limit.RateLimitMiddleware` aplica janela deslizante em `/api/*`
  (`RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`).
- **Isolamento do navegador**: Chromium roda apenas com o perfil em `shortcut_data/`,
  sem credenciais no código.

---

## 8. Pontos de extensão

- **OpenRouter** (`openrouter/client.py`): resumos de mensagem e sugestões de resposta;
  ligado com `OPENROUTER_ENABLED=true` + `OPENROUTER_API_KEY`. Nunca derruba o fluxo —
  em falha o código segue com o texto original.
- **Novos comandos de voz**: acrescente palavras nos sets de `flow_orchestrator`.
- **Novas colunas**: `kanban/models.COLUMN_ORDER` + `state_manager.ALLOWED_TRANSITIONS`.
