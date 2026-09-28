# Shortcut — Plano de Deploy

## Resumo executivo

| Peça | Onde rodar | Por quê |
| --- | --- | --- |
| **Frontend** | **Vercel** (estático) | É um bundle Vite/React puro — sem estado. |
| **Backend** | **Railway, Fly.io ou VPS** | Precisa de **processo persistente**: Chromium (Playwright) + modelo Whisper + microfone/TTS. |

> ⚠️ **A Vercel sozinha NÃO comporta o backend.**
> Functions serverless têm limite de execução (~10–60 s), sistema de arquivos efêmero e
> não mantêm processos vivos — o Chromium do WhatsApp Web, o polling periódico e o modelo
> Whisper carregado em memória **exigem um processo contínuo**. Por isso o backend Python
> fica hospedado separadamente (abaixo).

---

## 1. Frontend na Vercel

```bash
cd frontend
npm install
npm run build       # gera frontend/dist
npx vercel --prod   # ou conecte o repositório no painel da Vercel
```

Configurações no painel:

- **Framework preset:** Vite
- **Build command:** `npm run build`
- **Output directory:** `dist`
- **Environment variable:** `VITE_BACKEND_URL=https://<seu-backend>.up.railway.app`

> O `vite.config.ts` usa `VITE_BACKEND_URL` apenas para o proxy em dev; em produção o
> `services/api.ts` também usa `VITE_BACKEND_URL` como prefixo das chamadas.
> **Não há SSR** — nada impede o deploy estático.

---

## 2. Backend (processo persistente)

O backend é um processo longo: Chromium + polling + Whisper em memória.
Escolha uma das opções:

### 2.1 Railway

```toml
# railway.toml (raiz do backend)
[build]
builder = "nixpacks"

[deploy]
startCommand = "python run_backend.py"
healthcheckPath = "/api/health"
```

- Plano com **volume persistente** montado em `/data` (para `shortcut_data/` — perfil do
  WhatsApp e áudios). Sem volume, o QR precisaria ser escaneado a cada deploy.
- Variáveis de ambiente: as mesmas do `.env.example` + `SHORTCUT_MASTER_KEY` + `.env.enc`
  carregado como *secret file* (ou apenas as variáveis diretas).
- **Limitação importante:** o WhatsApp exige uma **interface gráfica**. Prefira
  `HEADLESS=false` com um display virtual (Xvfb) ou use a opção headless testada.

### 2.2 Fly.io (recomendado para Playwright)

```yaml
# fly.toml
app = "shortcut-backend"
[build]
  [build.args]
[http_service]
  internal_port = 8000
  force_https = true
[[vm]]
  memory = "2gb"
  cpu_kind = "shared"
  cpus = 2
```

- Fly suporta **Xvfb + Chromium** bem (imagem com `chromium` e `xvfb-run`).
- `fly volumes create shortcut_data --size 5` → monte em `/data` e aponte
  `SHORTCUT_DATA_DIR=/data`.
- Whisper `small` em CPU: use `WHISPER_MODEL=base` ou `tiny` se a VM for pequena.

### 2.3 VPS (DigitalOcean / Hetzner / AWS EC2) — mais simples e barato

```bash
# Ubuntu 22.04+
sudo apt update && sudo apt install -y python3.11 python3.11-venv nodejs npm xvfb
git clone <repo> && cd shortcut

# systemd unit (etc/systemd/system/shortcut.service)
[Unit]
Description=Shortcut backend
After=network.target

[Service]
WorkingDirectory=/opt/shortcut/backend
EnvironmentFile=/opt/shortcut/backend/.env
ExecStart=/usr/bin/xvfb-run -a .venv/bin/python run_backend.py
Restart=always
User=shortcut

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now shortcut
# frontend: build estático servido por nginx ou na Vercel
```

---

## 3. Configuração de ambiente em produção

| Variável | Produção |
| --- | --- |
| `BACKEND_HOST` | `0.0.0.0` |
| `FRONTEND_ORIGIN` | `https://<app>.vercel.app` (CORS) |
| `HEADLESS` | `true` (com Xvfb) ou `false` (com display) |
| `WHATSAPP_USER_DATA_DIR` | dentro do volume persistente |
| `SHORTCUT_MASTER_KEY` | **somente** no secret manager da plataforma |
| `OPENROUTER_API_KEY` | opcional |

CORS já é liberado para `FRONTEND_ORIGIN` via `app/main.py`.

---

## 4. Checklist antes do deploy

- [ ] `.env`, `.env.enc`, `*.key` fora do git (`.gitignore`)
- [ ] `SHORTCUT_MASTER_KEY` definida no ambiente da plataforma (não no repositório)
- [ ] volume persistente apontando para `SHORTCUT_DATA_DIR`
- [ ] `GET /api/health` respondendo `{"status":"ok"}`
- [ ] primeiro login: escanear QR **uma única vez** (o perfil fica salvo no volume)
- [ ] HTTPS no backend (Railway/Fly fazem automaticamente)
- [ ] rate limit calibrado (`RATE_LIMIT_REQUESTS`)

---

## 5. Arquitetura alvo (fase 2)

```
        Vercel (frontend estático)
                 │  REST + WSS
                 ▼
   Backend persistente (Fly.io / Railway / VPS)
      ├── FastAPI + WebSocket
      ├── Playwright + Xvfb (WhatsApp Web)
      ├── faster-whisper (CPU/GPU)
      └── Volume: shortcut_data (sessão + áudios)
```

Nada no frontend precisa mudar: basta apontar `VITE_BACKEND_URL` para o novo host.
