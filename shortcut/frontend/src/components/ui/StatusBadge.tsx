import type { WhatsAppStatusId } from "../../types";

const LABELS: Record<WhatsAppStatusId, string> = {
  connected: "Conectado",
  waiting_qr: "Aguardando QR Code",
  starting: "Iniciando…",
  error: "Erro de conexão",
  stopped: "Desligado",
};

const DOTS: Record<WhatsAppStatusId, string> = {
  connected: "online",
  waiting_qr: "away",
  starting: "busy",
  error: "busy",
  stopped: "offline",
};

/** Indicador de status estilo MSN (bolinha + legenda). */
export function StatusBadge({ status }: { status: WhatsAppStatusId }) {
  return (
    <span className={`status-badge status-badge--${DOTS[status]}`} title={LABELS[status]}>
      <span className="status-badge__dot" aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
