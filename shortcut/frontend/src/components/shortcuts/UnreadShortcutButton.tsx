import { useState } from "react";
import { RetroButton } from "../ui/RetroButton";

interface UnreadShortcutButtonProps {
  unreadCount: number;
  flowActive: boolean;
  onAnnounce: () => Promise<unknown>;
  onStartFlow: () => Promise<unknown>;
  onStopFlow: () => Promise<unknown>;
}

/** Botão flutuante "Você tem X mensagens não lidas…". */
export function UnreadShortcutButton({
  unreadCount,
  flowActive,
  onAnnounce,
  onStartFlow,
  onStopFlow,
}: UnreadShortcutButtonProps) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const announce = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = (await onAnnounce()) as { message?: string };
      setMessage(result?.message ?? null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao anunciar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="shortcut" aria-label="Atalho de mensagens não lidas">
      {message && <div className="shortcut__toast">{message}</div>}
      <div className="shortcut__panel">
        <RetroButton variant="primary" icon="📣" onClick={() => void announce()} disabled={busy}>
          {busy
            ? "Ouvindo…"
            : `Você tem ${unreadCount} mensagem${unreadCount === 1 ? "" : "s"} não lida${unreadCount === 1 ? "" : "s"}`}
        </RetroButton>
        <div className="shortcut__flow">
          <RetroButton variant="success" icon="▶" onClick={() => void onStartFlow()}>
            Ler agora
          </RetroButton>
          <RetroButton variant="danger" icon="■" onClick={() => void onStopFlow()}>
            Parar
          </RetroButton>
        </div>
        {flowActive && (
          <span className="shortcut__live">
            <span className="shortcut__live-dot" aria-hidden="true" /> esteira ativa
          </span>
        )}
      </div>
    </aside>
  );
}
