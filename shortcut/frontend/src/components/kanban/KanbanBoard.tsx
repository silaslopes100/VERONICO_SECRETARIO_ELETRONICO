import type { KanbanStore } from "../../hooks/useKanbanState";
import { KanbanColumn } from "./KanbanColumn";
import { UnreadShortcutButton } from "../shortcuts/UnreadShortcutButton";

interface KanbanBoardProps {
  store: KanbanStore;
  playingId: string | null;
  replyingId: string | null;
  onPlay: (cardId: string) => void;
  onReply: (cardId: string) => void;
}

/** Quadro Kanban com as 4 colunas fixas + botão de atalho de mensagens. */
export function KanbanBoard({ store, playingId, replyingId, onPlay, onReply }: KanbanBoardProps) {
  return (
    <div className="board">
      <div className="board__columns">
        {store.columns.map((column) => (
          <KanbanColumn
            key={column.id}
            column={column}
            cards={column.cardIds
              .map((id) => store.cards[id])
              .filter((card): card is NonNullable<typeof card> => Boolean(card) && !card.archived)}
            freshIds={store.freshCardIds}
            playingId={playingId}
            replyingId={replyingId}
            onPlay={(card) => onPlay(card.id)}
            onReply={(card) => onReply(card.id)}
            onArchive={(card) => void store.archiveCard(card.id)}
            onMove={(card, target) => void store.moveCard(card.id, target)}
          />
        ))}
      </div>
      <UnreadShortcutButton
        unreadCount={store.unreadCount}
        flowActive={store.flow?.active ?? false}
        onAnnounce={store.announceUnread}
        onStartFlow={store.startFlow}
        onStopFlow={store.stopFlow}
      />
    </div>
  );
}
