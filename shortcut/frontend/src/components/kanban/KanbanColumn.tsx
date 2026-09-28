import type { Card, Column, ColumnId } from "../../types";
import { ConversationCard } from "./ConversationCard";

interface KanbanColumnProps {
  column: Column;
  cards: Card[];
  freshIds: string[];
  playingId: string | null;
  replyingId: string | null;
  onPlay: (card: Card) => void;
  onReply: (card: Card) => void;
  onArchive: (card: Card) => void;
  onMove: (card: Card, column: ColumnId) => void;
}

/** Coluna do quadro com contador e pilha de cards. */
export function KanbanColumn({
  column,
  cards,
  freshIds,
  playingId,
  replyingId,
  onPlay,
  onReply,
  onArchive,
  onMove,
}: KanbanColumnProps) {
  return (
    <section className="column" aria-label={column.title}>
      <header className="column__header">
        <h2 className="column__title">{column.title}</h2>
        <span className="column__count">{cards.length}</span>
      </header>
      <div className="column__body">
        {cards.length === 0 ? (
          <p className="column__empty">Nenhum card aqui.</p>
        ) : (
          cards.map((card) => (
            <ConversationCard
              key={card.id}
              card={card}
              fresh={freshIds.includes(card.id)}
              playing={playingId === card.id}
              replying={replyingId === card.id}
              onPlay={onPlay}
              onReply={onReply}
              onArchive={onArchive}
              onMove={onMove}
            />
          ))
        )}
      </div>
    </section>
  );
}
