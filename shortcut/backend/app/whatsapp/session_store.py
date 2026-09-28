"""Persistência da sessão do WhatsApp Web (profile do Chromium).

O ``user-data-dir`` mantém os cookies/localStorage do WhatsApp, evitando
que o QR Code precise ser escaneado novamente a cada reinício.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

META_FILE = "session_meta.json"


class SessionStore:
    """Controla o diretório de perfil e metadados da sessão."""

    def __init__(self, profile_dir: Path | None = None) -> None:
        self.profile_dir = profile_dir or get_settings().whatsapp_user_data_dir
        self.meta_path = self.profile_dir / META_FILE

    def ensure(self) -> Path:
        """Cria o diretório de perfil se não existir."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        return self.profile_dir

    @property
    def has_session(self) -> bool:
        """Indica se já existe um perfil salvo (possível sessão válida)."""
        if not self.profile_dir.exists():
            return False
        return any(self.profile_dir.iterdir())

    def read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def write_meta(self, **updates: Any) -> dict[str, Any]:
        meta = self.read_meta()
        meta.update(updates)
        meta["updated_at"] = time.time()
        self.ensure()
        self.meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")
        return meta

    def mark_logged_in(self) -> None:
        self.write_meta(logged_in=True, last_login_at=time.time())
        logger.info("Sessão do WhatsApp marcada como autenticada.")

    def mark_logged_out(self) -> None:
        self.write_meta(logged_in=False, last_logout_at=time.time())

    def clear(self) -> None:
        """Remove a sessão salva (força novo QR Code)."""
        import shutil

        if self.profile_dir.exists():
            shutil.rmtree(self.profile_dir, ignore_errors=True)
        self.ensure()
        logger.info("Sessão do WhatsApp removida.")


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
