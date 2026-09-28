"""Criptografia/descriptografia do arquivo .env com Fernet.

A chave mestra NUNCA é gravada em arquivo: ela é lida exclusivamente da
variável de ambiente do sistema operacional ``SHORTCUT_MASTER_KEY``.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MASTER_KEY_ENV = "SHORTCUT_MASTER_KEY"


class EnvCryptoError(RuntimeError):
    """Erro de criptografia/descriptografia do arquivo de ambiente."""


def _load_master_key() -> bytes:
    key = os.environ.get(MASTER_KEY_ENV, "").strip()
    if not key:
        raise EnvCryptoError(
            f"Variável de ambiente {MASTER_KEY_ENV} ausente ou vazia. "
            f"Defina-a no sistema operacional, ex.: "
            f"python -c \"import secrets;print(secrets.token_urlsafe(32))\""
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise EnvCryptoError(
            f"{MASTER_KEY_ENV} não é uma chave Fernet válida. Gere uma nova com: "
            "python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\""
        ) from exc


def _fernet() -> Fernet:
    return _load_master_key()


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Cifra bytes brutos e devolve o token Fernet."""
    return _fernet().encrypt(plaintext)


def decrypt_bytes(token: bytes) -> bytes:
    """Decifra um token Fernet; levanta :class:`EnvCryptoError` em falha."""
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise EnvCryptoError(
            "Falha ao decifrar: chave mestra incorreta ou .env.enc corrompido."
        ) from exc


def encrypt_file(source: Path, destination: Path) -> Path:
    """Cifra ``source`` (texto puro) para ``destination`` (``.env.enc``)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encrypt_bytes(source.read_bytes()))
    return destination


def decrypt_file(source: Path, destination: Path | None = None) -> bytes:
    """Decifra ``source``; devolve os bytes ou grava em ``destination``."""
    if not source.exists():
        raise EnvCryptoError(f"Arquivo cifrado não encontrado: {source}")
    plaintext = decrypt_bytes(source.read_bytes())
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(plaintext)
    return plaintext


def parse_env_bytes(raw: bytes) -> dict[str, str]:
    """Converte o conteúdo de um ``.env`` em dicionário de variáveis."""
    result: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result
