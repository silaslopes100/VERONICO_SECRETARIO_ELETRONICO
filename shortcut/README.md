# Shortcut 📞

**Secretária eletrônica pessoal para WhatsApp Web** — com automação de voz completa:

- **fala → texto → envio** (você fala, o Whisper transcreve, o Playwright envia no WhatsApp);
- **texto → fala → escuta** (mensagens de áudio recebidas são transcritas e lidas em voz alta).

Tudo organizado em um **quadro Kanban** com estética nostálgica **anos 2000 / MSN Messenger**,
rodando 24/7 em `localhost`.

---

## ✨ Funcionalidades

| Recurso | Como funciona |
| --- | --- |
| Login sem QR repetido | Sessão persistente em `user-data-dir` do Chromium |
| Leitura da caixa | `inbox_reader.py` varre conversas não lidas na sidebar |
| Áudio recebido | `audio_extractor.py` baixa → `whisper_transcriber.py` transcreve |
| Botão **Play** | TTS lê a transcrição da mensagem em voz alta |
| Botão **Responder** | Mic no navegador → Whisper → texto injetado e enviado no WhatsApp |
| Botão **Arquivar** | Arquiva a conversa real no WhatsApp (coluna *Respondidas*) |
| Atalho "Você tem X mensagens…" | TTS pergunta; "sim" inicia a leitura sequencial (esteira) |
| Tempo real | WebSocket atualiza o Kanban a cada mudança de estado |

**Colunas fixas:** `Nova mensagem → Ouvidas → Aguardando resposta → Respondidas`

---

## 🧰 Stack

- **Backend:** Python 3.11+ · FastAPI · Playwright (Chromium) · faster-whisper · pyttsx3 · sounddevice · (opcional) OpenRouter
- **Frontend:** Vite · React · TypeScript · tema MSN retrô (CSS próprio)
- **Segurança:** `.env` cifrado (`.env.enc`, Fernet) + chave mestra `SHORTCUT_MASTER_KEY` só no ambiente do SO

---

## 🚀 Início rápido

```bash
# 1. (opcional, só para .env.enc) gere a chave mestra e exporte no SO:
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
#   Windows (PowerShell, por sessão):
#     $env:SHORTCUT_MASTER_KEY = "<cole a chave>"
#   Linux/macOS:
#     export SHORTCUT_MASTER_KEY="<cole a chave>"

# 2. suba tudo (instala venv, requirements, Chromium, npm install, sobe os dois servidores)
powershell -ExecutionPolicy Bypass -File launcher\start.ps1     # Windows
./launcher/start.sh                                              # Linux/macOS
```

Na **primeira execução** o Chromium abre o `https://web.whatsapp.com/` — **escaneie o QR Code uma vez**.
Nas próximas vezes a sessão é reutilizada.

### URLs

- Frontend: **http://localhost:5173**
- Backend: **http://localhost:8000** (docs interativos em `/docs`)

### Comandos úteis

```bash
# dependências isoladas
python launcher/install_dependencies.py

# testes do backend
cd backend && python -m pytest

# typecheck/build do frontend
cd frontend && npm run typecheck && npm run build
```

---

## 🗣 Comandos de voz (documentação resumida)

O fluxo de leitura sequencial entende (pt-BR, acentos irrelevantes):

| Comando | Ação |
| --- | --- |
| **sim** / *pode ser* / *vamos lá* | Inicia a leitura das mensagens não lidas |
| **próxima** / *pula* | Passa para o próximo card da fila |
| **responder** / *responda* | Grava sua resposta → envia como texto no WhatsApp |
| **arquivar** | Arquiva a conversa (card na coluna *Respondidas*) |
| **não** / *parar* | Encerra o fluxo |

Sem comando (silêncio/timeout), a esteira avança automaticamente para o próximo card.
Detalhes completos em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🔐 Segurança

1. **Nunca** commite `.env`, `.env.enc` ou `*.key` (já estão no `.gitignore`).
2. Use `.env.example` como modelo.
3. Se for usar `.env.enc`:
   ```bash
   # gere a chave (uma vez) e guarde no ambiente do SO, nunca em arquivo:
   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
   # cifre o .env:
   python -c "from pathlib import Path; from app.security.env_crypto import encrypt_file; encrypt_file(Path('.env'), Path('.env.enc'))"  # rode em backend/
   ```
   O backend decifra **em memória** no boot (`secrets_loader.py`) usando `SHORTCUT_MASTER_KEY`.
4. Todo texto vindo do WhatsApp é sanitizado no backend (remoção de HTML/controle) e renderizado como texto pelo React — dupla proteção contra XSS.
5. Rate limiting básico (janela deslizante) nas rotas `/api/*`.

---

## 📁 Estrutura

```
shortcut/
├── backend/            # FastAPI + Playwright + Whisper + TTS
│   ├── app/
│   │   ├── main.py     # só composição (rotas/middleware/lifecycle)
│   │   ├── config.py   # settings validados
│   │   ├── security/   # .env.enc (Fernet) + carga de segredos
│   │   ├── whatsapp/   # navegador, inbox, áudio, envio, arquivamento
│   │   ├── audio/      # whisper, mic do usuário, TTS
│   │   ├── kanban/     # modelos, estado, esteira de fluxo
│   │   ├── api/        # REST + WebSocket + rate limit
│   │   └── openrouter/ # cliente opcional de IA
│   ├── tests/
│   ├── requirements.txt
│   └── run_backend.py
├── frontend/           # Vite + React + TS (tema MSN)
├── launcher/           # start.ps1, start.sh, install_dependencies.py
├── docs/               # ARCHITECTURE.md e DEPLOYMENT.md
├── .env.example
└── README.md
```

---

## 🌐 Deploy

O frontend é estático (Vercel), mas o **backend exige processo persistente**
(Playwright + Whisper não rodam em functions serverless) — por isso ele vai para
Railway / Fly.io / VPS. Plano completo em [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## 🧪 Testes

```bash
cd backend
python -m pytest
```

Cobrem: sanitização/leitura do inbox, envio de mensagens e o transcritor Whisper
(com modelos/mock — sem tocar no navegador real).
