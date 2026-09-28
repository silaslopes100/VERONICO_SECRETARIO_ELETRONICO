"""Leitura e validação das variáveis de ambiente do backend."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.security.secrets_loader import load_secrets

BASE_DIR = Path(__file__).resolve().parents[2]  # .../backend
PROJECT_ROOT = BASE_DIR.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        logging.warning("Valor inválido para %s=%r; usando %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _env_path(name: str, default: str) -> Path:
    raw = _env(name, default)
    path = Path(raw)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


@dataclass(frozen=True)
class Settings:
    """Configuração imutável do backend, validada uma única vez no boot."""

    host: str = "127.0.0.1"
    port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"

    whatsapp_url: str = "https://web.whatsapp.com/"
    whatsapp_user_data_dir: Path = field(default_factory=lambda: BASE_DIR / "shortcut_data" / "whatsapp-profile")
    headless: bool = False
    poll_interval_seconds: int = 15

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    tts_rate: int = 175
    tts_voice_index: int = -1

    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_max_seconds: int = 30

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_enabled: bool = False

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    data_dir: Path = field(default_factory=lambda: BASE_DIR / "shortcut_data")

    @classmethod
    def load(cls) -> "Settings":
        """Carrega segredos e monta as configurações validadas."""
        load_secrets(PROJECT_ROOT)
        logging.basicConfig(
            level=getattr(logging, _env("LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
        settings = cls(
            host=_env("BACKEND_HOST", "127.0.0.1"),
            port=_env_int("BACKEND_PORT", 8000),
            frontend_origin=_env("FRONTEND_ORIGIN", "http://localhost:5173"),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            whatsapp_url=_env("WHATSAPP_URL", "https://web.whatsapp.com/"),
            whatsapp_user_data_dir=_env_path(
                "WHATSAPP_USER_DATA_DIR", "../shortcut_data/whatsapp-profile"
            ),
            headless=_env_bool("HEADLESS", False),
            poll_interval_seconds=max(5, _env_int("POLL_INTERVAL_SECONDS", 15)),
            whisper_model=_env("WHISPER_MODEL", "small"),
            whisper_device=_env("WHISPER_DEVICE", "cpu"),
            whisper_compute_type=_env("WHISPER_COMPUTE_TYPE", "int8"),
            tts_rate=_env_int("TTS_RATE", 175),
            tts_voice_index=_env_int("TTS_VOICE_INDEX", -1),
            audio_sample_rate=_env_int("AUDIO_SAMPLE_RATE", 16000),
            audio_channels=max(1, _env_int("AUDIO_CHANNELS", 1)),
            audio_max_seconds=max(5, _env_int("AUDIO_MAX_SECONDS", 30)),
            openrouter_api_key=_env("OPENROUTER_API_KEY"),
            openrouter_model=_env("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            openrouter_enabled=_env_bool("OPENROUTER_ENABLED", False),
            rate_limit_requests=max(1, _env_int("RATE_LIMIT_REQUESTS", 120)),
            rate_limit_window_seconds=max(1, _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)),
            data_dir=_env_path("SHORTCUT_DATA_DIR", "shortcut_data"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Valida invariantes críticos; levanta ``ValueError`` em config inválida."""
        if not (1 <= self.port <= 65535):
            raise ValueError(f"BACKEND_PORT inválido: {self.port}")
        if not self.whatsapp_url.startswith("https://"):
            raise ValueError("WHATSAPP_URL precisa começar com https://")
        if self.audio_channels not in (1, 2):
            raise ValueError("AUDIO_CHANNELS deve ser 1 ou 2")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.whatsapp_user_data_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton das configurações."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
