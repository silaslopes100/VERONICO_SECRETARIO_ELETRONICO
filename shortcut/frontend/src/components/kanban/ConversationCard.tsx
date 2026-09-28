import type { Card, ColumnId } from "../../types";
import { RetroButton } from "../ui/RetroButton";

interface ConversationCardProps {
  card: Card;
  fresh?: boolean;
  playing?: boolean;
  replying?: boolean;
  onPlay: (card: Card) => void;
  onReply: (card: Card) => void;
  onArchive: (card: Card) => void;
  onMove: (card: Card, column: ColumnId) => void;
}

const NEXT_ORDER: Record<ColumnId, ColumnId | null> = {
  new: "heard",
  heard: "waiting_reply",
  waiting_reply: "responded",
  responded: null,
};

const PREV_ORDER: Record<ColumnId, ColumnId | null> = {
  new: null,
  heard: "new",
  waiting_reply: "heard",
  responded: "waiting_reply",
};

/** Card de conversa com Play (TTS), Responder (voz) e Arquivar. */
export function ConversationCard({
  card,
  fresh,
  playing,
  replying,
  onPlay,
  onReply,
  onArchive,
  onMove,
}: ConversationCardProps) {
  const next = NEXT_ORDER[card.column];
  const prev = PREV_ORDER[card.column];
  const text = card.transcript || card.preview;

  return (
    <article className={`card ${fresh ? "card--fresh" : ""}`}>
      <header className="card__header">
        <span className="card__avatar" aria-hidden="true">
          {card.contact.slice(0, 1).toUpperCase()}
        </span>
        <div className="card__title">
          <strong className="card__contact" title={card.contact}>
            {card.contact}
          </strong>
          <span className="card__meta">
            {card.timestamp || "agora"}
            {card.unreadCount > 1 ? ` · ${card.unreadCount} não lidas` : ""}
            {card.isAudio ? " · 🎤 áudio" : ""}
          </span>
        </div>
      </header>

      <p className="card__preview" title={text}>
        {text || "(mensagem sem conteúdo)"}
      </p>

      {card.replyText && (
        <p className="card__reply" title={card.replyText}>
          ↩ Você: {card.replyText}
        </p>
      )}

      <footer className="card__actions">
        <RetroButton
          variant="primary"
          icon={playing ? "❚❚" : "▶"}
          onClick={() => onPlay(card)}
          title="Ouvir a mensagem (TTS)"
          aria-label={`Ouvir mensagem de ${card.contact}`}
        />
        <RetroButton
          variant="success"
          icon="🎤"
          onClick={() => onReply(card)}
          disabled={replying}
          title="Responder por voz"
          aria-label={`Responder ${card.contact}`}
        >
          {replying ? "Ouvindo…" : "Responder"}
        </RetroButton>
        {prev && (
          <RetroButton
            variant="ghost"
            icon="◀"
            onClick={() => onMove(card, prev)}
            title="Mover para a coluna anterior"
            aria-label="Mover card para a coluna anterior"
          />
        )}
        {next && (
          <RetroButton
            variant="ghost"
            icon="▶"
            onClick={() => onMove(card, next)}
            title="Mover para a próxima coluna"
            aria-label="Mover card para a próxima coluna"
          />
        )}
        {card.column === "responded" && (
          <RetroButton
            variant="danger"
            icon="📦"
            onClick={() => onArchive(card)}
            title="Arquivar conversa no WhatsApp"
            aria-label={`Arquivar conversa com ${card.contact}`}
          >
            Arquivar
          </RetroButton>
        )}
      </footer>
    </article>
  );
}
