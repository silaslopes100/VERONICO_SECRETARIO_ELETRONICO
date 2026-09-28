"""Ponto de entrada único do backend (chamado pelo launcher).

Uso: ``python run_backend.py`` (a partir de ``backend/``).

Inclui verificação prévia da porta para evitar instâncias duplicadas:
- já há um Shortcut de pé  -> reaproveita (exit 0);
- há outro programa na porta -> erro claro (exit 1).
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

import uvicorn

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _probe_host(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "::", "") else host


def _listening(host: str, port: int) -> bool:
    """Indica se alguém já está aceitando conexões na porta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((_probe_host(host), port)) == 0


def _healthy_backend(host: str, port: int) -> bool:
    """Confirma que quem escuta a porta é outro Shortcut (não outro app)."""
    url = f"http://{_probe_host(host)}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("service") == "shortcut-backend"
    except Exception:  # noqa: BLE001 - qualquer falha = não é o nosso backend
        return False


def main() -> None:
    from app.config import get_settings

    settings = get_settings()
    host, port = settings.host, settings.port

    if _healthy_backend(host, port):
        print(
            f"Shortcut já está rodando em http://{_probe_host(host)}:{port} — "
            "reutilizando a instância existente (nada a fazer)."
        )
        raise SystemExit(0)
    if _listening(host, port):
        print(
            f"ERRO: porta {port} já está em uso por outro programa. "
            f"Mate o processo ou altere BACKEND_PORT em .env."
        )
        raise SystemExit(1)

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=False,
            log_level=settings.log_level.lower(),
            ws_ping_interval=20,
        )
    finally:
        # Garante que o processo termine mesmo com threads residuais (TTS/Playwright).
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
