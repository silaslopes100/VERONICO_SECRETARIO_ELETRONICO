"""Carrega segredos em runtime (``.env`` claro ou ``.env.enc`` cifrado).

Ordem de precedência:
1. Variáveis já presentes no ambiente do processo (não são sobrescritas).
2. ``.env`` claro (desenvolvimento local), se existir.
3. ``.env.enc`` cifrado — decifrado em memória usando SHORTCUT_MASTER_KEY.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.security.env_crypto import decrypt_file, parse_env_bytes

logger = logging.getLogger(__name__)

_LOADED = False


def load_secrets(root: Path | None = None, *, force: bool = False) -> dict[str, str]:
    """Carrega segredos no ``os.environ`` sem sobrescrever valores existentes."""
    global _LOADED
    if _LOADED and not force:
        return {}

    root = root or Path(__file__).resolve().parents[3]
    loaded: dict[str, str] = {}

    plain_env = root / ".env"
    encrypted_env = root / ".env.enc"

    raw: bytes | None = None
    if plain_env.exists():
        raw = plain_env.read_bytes()
        logger.info("Carregando segredos de %s", plain_env)
    elif encrypted_env.exists():
        try:
            raw = decrypt_file(encrypted_env)
            logger.info("Segredos de %s decifrados em memória.", encrypted_env)
        except Exception as exc:  # noqa: BLE001 - repassa erro claro ao operador
            logger.error("Não foi possível decifrar %s: %s", encrypted_env, exc)
            raise

    if raw is not None:
        for key, value in parse_env_bytes(raw).items():
            if key not in os.environ:
                os.environ[key] = value
                loaded[key] = value

    _LOADED = True
    return loaded


def get_secret(name: str, default: str | None = None) -> str | None:
    """Consulta um segredo já carregado (ou direto do ambiente)."""
    return os.environ.get(name, default)
