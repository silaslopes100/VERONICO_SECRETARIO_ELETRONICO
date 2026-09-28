#!/usr/bin/env bash
# =============================================================================
# Shortcut — launcher para Linux/macOS
# 1) instala dependências  2) encerra instâncias antigas do projeto
# 3) sobe backend (8000) + frontend (5173) com health check
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$ROOT/launcher"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"
BACKEND_URL="http://127.0.0.1:8000/api/health"
FRONTEND_URL="http://127.0.0.1:5173"

echo "=== Shortcut ==="

# --------------------------------------------------------------- pré-requisitos
PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.11+ nao encontrado. Instale: https://python.org" >&2; exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 18+ nao encontrado. Instale: https://nodejs.org" >&2; exit 1
fi

# --------------------------------------------------------------- dependências
echo "[1/6] Instalando dependencias (primeira vez pode demorar)..."
"$PYTHON_BIN" "$LAUNCHER/install_dependencies.py"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtualenv nao foi criado em $VENV_PY" >&2; exit 1
fi

# ---------------------------------------------- instâncias antigas do projeto
echo "[2/6] Encerrando instancias antigas do Shortcut (se houver)..."
pkill -f "$ROOT/backend/run_backend.py" 2>/dev/null || true
pkill -f "$ROOT/frontend.*vite" 2>/dev/null || true
sleep 2

if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':8000 '; then
  echo "   ! A porta 8000 ainda esta ocupada por outro programa." >&2
  echo "     Encerre esse programa ou altere BACKEND_PORT em .env" >&2
  exit 1
fi

# --------------------------------------------------------- .env de exemplo
if [[ ! -f "$ROOT/.env" && -f "$ROOT/.env.example" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Criado .env a partir de .env.example."
fi
if [[ -z "${SHORTCUT_MASTER_KEY:-}" ]]; then
  echo "Aviso: SHORTCUT_MASTER_KEY nao definida (obrigatoria para .env.enc). Consulte o README."
fi

# ------------------------------------------------------------------- servers
echo "[3/6] Subindo backend (FastAPI + Playwright)..."
(cd "$BACKEND" && "$VENV_PY" run_backend.py) &
BACKEND_PID=$!

echo "[4/6] Aguardando o health check do backend..."
backend_ok=0
for _ in $(seq 1 15); do
  sleep 2
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then break; fi
  if curl -fsS --max-time 2 "$BACKEND_URL" 2>/dev/null | grep -q 'shortcut-backend'; then
    backend_ok=1; break
  fi
done
if [[ "$backend_ok" -ne 1 ]]; then
  echo "Backend nao subiu (porta 8000 nao respondeu /api/health)." >&2
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi
echo "   backend OK em $BACKEND_URL"

echo "[5/6] Subindo frontend (Vite)..."
(cd "$FRONTEND" && npm run dev) &
FRONTEND_PID=$!

frontend_ok=0
for _ in $(seq 1 15); do
  sleep 2
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then break; fi
  if curl -fsS --max-time 2 "$FRONTEND_URL" >/dev/null 2>&1; then
    frontend_ok=1; break
  fi
done
if [[ "$frontend_ok" -ne 1 ]]; then
  echo "Frontend nao subiu em $FRONTEND_URL." >&2
  kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

echo "[6/6] Tudo no ar!"
cat <<'MSG'

Shortcut no ar!
  Frontend : http://localhost:5173
  Backend  : http://localhost:8000 (docs em /docs)
  WhatsApp : escaneie o QR Code na janela Chromium aberta pelo backend.
  Encerrar : Ctrl+C nesta janela.
MSG

# ------------------------------------------------------------------- shutdown
cleanup() {
  echo
  echo "Encerrando processos do Shortcut..."
  kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  pkill -P "$FRONTEND_PID" 2>/dev/null || true
  pkill -P "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "Ate logo!"
}
trap cleanup INT TERM EXIT

wait
