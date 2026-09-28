"""Instala todas as dependências do projeto Shortcut.

Executado por ``start.ps1``/``start.sh`` (e manualmente quando quiser):

1. Cria o virtualenv ``backend/.venv`` (se não existir).
2. Instala ``backend/requirements.txt``.
3. Instala o Chromium do Playwright (``playwright install chromium``).
4. Roda ``npm install`` em ``frontend/``.
5. Verifica a chave mestra ``SHORTCUT_MASTER_KEY`` (aviso, não bloqueia).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
VENV_PYTHON = VENV / ("Scripts" if os.name == "nt" else "bin") / (
    "python.exe" if os.name == "nt" else "python"
)


def _run(cmd: list[str], *, cwd: Path | None = None, optional: bool = False) -> bool:
    print(f"\n$ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=False)
    except OSError as exc:
        print(f"  ! falha ao executar: {exc}")
        return optional
    if result.returncode != 0:
        print(f"  ! código de saída {result.returncode}")
        return optional
    return True


def ensure_venv() -> Path:
    if VENV_PYTHON.exists():
        print(f"[1/5] Virtualenv já existe: {VENV}")
        return VENV_PYTHON
    print("[1/5] Criando virtualenv…")
    if not _run([sys.executable, "-m", "venv", str(VENV)]):
        raise SystemExit("Não foi possível criar o virtualenv.")
    return VENV_PYTHON


def install_python_deps() -> None:
    print("[2/5] Instalando dependências do backend…")
    ok = _run(
        [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip", "--quiet"]
    ) and _run(
        [
            str(VENV_PYTHON),
            "-m",
            "pip",
            "install",
            "-r",
            str(BACKEND / "requirements.txt"),
            "--quiet",
        ]
    )
    if not ok:
        raise SystemExit("Falha ao instalar requirements.txt")


def install_playwright_browser() -> None:
    print("[3/5] Instalando Chromium do Playwright…")
    ok = _run(
        [str(VENV_PYTHON), "-m", "playwright", "install", "chromium"],
        optional=True,
    )
    if not ok:
        print("  ! Aviso: navegador não instalado agora; rode manualmente:")
        print("    .venv/Scripts/python -m playwright install chromium")


def install_frontend_deps() -> None:
    print("[4/5] Instalando dependências do frontend…")
    npm = shutil.which("npm")
    if npm is None:
        print("  ! npm não encontrado — instale o Node.js 18+ e rode: npm install (em frontend/)")
        return
    if not _run([npm, "install"], cwd=FRONTEND):
        raise SystemExit("Falha ao rodar npm install no frontend")


def check_master_key() -> None:
    print("[5/5] Verificando SHORTCUT_MASTER_KEY…")
    if os.environ.get("SHORTCUT_MASTER_KEY"):
        print("  ✓ chave mestra presente no ambiente")
        return
    root_env = ROOT / ".env"
    if root_env.exists() or (ROOT / ".env.enc").exists():
        print(
            "  ! SHORTCUT_MASTER_KEY ausente. Defina no sistema operacional antes de "
            "usar .env.enc (veja README → Segurança)."
        )
    else:
        print("  - nenhum .env/.env.enc encontrado (modelo: .env.example)")


def main() -> None:
    ensure_venv()
    install_python_deps()
    install_playwright_browser()
    install_frontend_deps()
    check_master_key()
    print("\n✓ Dependências instaladas. Rode:  launcher/start.ps1 (Windows) ou start.sh (Linux/macOS)")


if __name__ == "__main__":
    main()
