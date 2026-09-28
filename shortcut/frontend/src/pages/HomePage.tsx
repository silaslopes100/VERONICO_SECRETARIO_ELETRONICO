import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import { RetroButton } from "../components/ui/RetroButton";
import { StatusBadge } from "../components/ui/StatusBadge";
import type { PageView, StatusResponse, WhatsAppStatusId } from "../types";

interface HomePageProps {
  onNavigate: (view: PageView) => void;
}

/** Tela de início: logo, status do WhatsApp e entrada para o Dashboard. */
export function HomePage({ onNavigate }: HomePageProps) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.getStatus());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend indisponível");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  const waStatus: WhatsAppStatusId = status?.whatsapp.status ?? "starting";

  return (
    <div className="home">
      <div className="window home__window">
        <div className="window__titlebar">
          <span className="window__title">Shortcut — Messenger</span>
          <span className="window__controls" aria-hidden="true">
            <span className="window__control">_</span>
            <span className="window__control">□</span>
            <span className="window__control window__control--close">×</span>
          </span>
        </div>
        <div className="window__body home__body">
          <div className="home__logo">
            <span className="home__logo-icon" aria-hidden="true">📞</span>
            <div>
              <h1 className="home__brand">Shortcut</h1>
              <p className="home__tagline">Sua secretária eletrônica pessoal para WhatsApp</p>
            </div>
          </div>

          <div className="home__status">
            <StatusBadge status={waStatus} />
            <span className="home__status-detail">
              {status?.whatsapp.last_error
                ? status.whatsapp.last_error
                : waStatus === "waiting_qr"
                  ? "Escaneie o QR Code no Chromium aberto para conectar."
                  : waStatus === "connected"
                    ? "WhatsApp Web conectado com sucesso."
                    : "Iniciando o navegador do WhatsApp…"}
            </span>
          </div>

          <p className="home__unread">
            📬 <strong>{status?.unread ?? 0}</strong> mensagem(ns) não lida(s)
          </p>

          {error && <p className="alert alert--error">{error}</p>}

          <div className="home__actions">
            <RetroButton variant="primary" icon="➡" onClick={() => onNavigate("dashboard")}>
              Entrar no Dashboard
            </RetroButton>
            <RetroButton variant="ghost" icon="🔄" onClick={() => void load()}>
              Atualizar status
            </RetroButton>
          </div>

          <p className="home__hint">
            Dica: fale com o botão 📣 no Dashboard — “sim” inicia a leitura das mensagens.
          </p>
        </div>
        <div className="window__statusbar">
          <span>Online</span>
          <span>localhost</span>
        </div>
      </div>
    </div>
  );
}
