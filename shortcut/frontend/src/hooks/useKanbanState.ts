import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import { useWebSocket } from "./useWebSocket";
import type {
  Card,
  ColumnId,
  FlowStatus,
  KanbanState,
  WhatsAppStatus,
} from "../types";

const EMPTY_STATE: KanbanState = { columns: [], cards: {}, unreadCount: 0, updatedAt: 0 };

/**
 * Estado central do Dashboard: Kanban + status do WhatsApp + fluxo de voz,
 * sincronizados em tempo real pelo WebSocket.
 */
export function useKanbanState() {
  const [state, setState] = useState<KanbanState>(EMPTY_STATE);
  const [whatsapp, setWhatsapp] = useState<WhatsAppStatus | null>(null);
  const [flow, setFlow] = useState<FlowStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const knownCardsRef = useRef<Set<string>>(new Set());
  const [freshCardIds, setFreshCardIds] = useState<string[]>([]);

  const handleEvent = useCallback((event: { type: string; payload: unknown }) => {
    if (event.type === "kanban_state") {
      const next = event.payload as KanbanState;
      const known = knownCardsRef.current;
      const fresh = Object.keys(next.cards).filter((id) => !known.has(id));
      Object.keys(next.cards).forEach((id) => known.add(id));
      setState(next);
      if (fresh.length > 0) setFreshCardIds((prev) => [...prev, ...fresh]);
    } else if (event.type === "whatsapp_status") {
      setWhatsapp(event.payload as WhatsAppStatus);
    } else if (event.type === "flow_status") {
      setFlow(event.payload as FlowStatus);
    }
  }, []);

  const { connected } = useWebSocket(handleEvent);

  const loadInitial = useCallback(async () => {
    try {
      setLoading(true);
      const [status, kanban] = await Promise.all([api.getStatus(), api.getState()]);
      setWhatsapp(status.whatsapp);
      setFlow(status.flow);
      setState(kanban);
      Object.keys(kanban.cards).forEach((id) => knownCardsRef.current.add(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend indisponível");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial, connected]);

  const moveCard = useCallback(async (cardId: string, column: ColumnId) => {
    try {
      await api.moveCard(cardId, column);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao mover card");
    }
  }, []);

  const archiveCard = useCallback(async (cardId: string) => {
    try {
      await api.archiveCard(cardId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao arquivar");
    }
  }, []);

  const replyByVoice = useCallback(async (cardId: string) => {
    const result = await api.replyByVoice(cardId);
    return result;
  }, []);

  const replyWithText = useCallback(
    async (cardId: string, text: string) => api.replyWithText(cardId, text),
    [],
  );

  const announceUnread = useCallback(() => api.announceUnread(), []);
  const startFlow = useCallback(() => api.startFlow(), []);
  const stopFlow = useCallback(() => api.stopFlow(), []);
  const refreshInbox = useCallback(() => api.refreshInbox(), []);
  const speakCard = useCallback((card: Card) => api.speak(card.transcript || card.preview), []);

  const cardsById = useMemo(() => state.cards, [state]);
  const columns = useMemo(() => state.columns, [state.columns]);

  const clearFresh = useCallback((ids: string[]) => {
    setFreshCardIds((prev) => prev.filter((id) => !ids.includes(id)));
  }, []);

  return {
    columns,
    cards: cardsById,
    unreadCount: state.unreadCount,
    whatsapp,
    flow,
    loading,
    error,
    connected,
    freshCardIds,
    clearFresh,
    refresh: loadInitial,
    moveCard,
    archiveCard,
    replyByVoice,
    replyWithText,
    announceUnread,
    startFlow,
    stopFlow,
    refreshInbox,
    speakCard,
  };
}

export type KanbanStore = ReturnType<typeof useKanbanState>;
