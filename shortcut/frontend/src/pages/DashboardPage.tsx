import { useCallback, useEffect, useRef, useState } from "react";
import { KanbanBoard } from "../components/kanban/KanbanBoard";
import { RetroButton } from "../components/ui/RetroButton";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useKanbanState } from "../hooks/useKanbanState";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import type { PageView } from "../types";

interface DashboardPageProps {
  onNavigate: (view: PageView) => void;
}

/** Dashboard Kanban: colunas, cards, atalho de voz e reprodução TTS. */
export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const store = useKanbanState();
  const { recordAndTranscribe, recording, error: recorderError } = useVoiceRecorder();
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [replyingId, setReplyingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const freshHandledRef = useRef<Set<string>>(new Set());

  // Sons de notificação estilo MSN para cards recém-chegados.
  useEffect(() => {
    const fresh = store.freshCardIds.filter((id) => !freshHandledRef.current.has(id));
    if (fresh.length === 0) return;
    fresh.forEach((id) => freshHandledRef.current.add(id));
    const audio = new Audio("/sounds/message.wav");
    void audio.play().catch(() => undefined);
    store.clearFresh(fresh);
  }, [store.freshCardIds, store]);

  const speakText = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return null;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "pt-BR";
    utterance.rate = 1.05;
    return utterance;
  }, []);

  const handlePlay = useCallback(
    (cardId: string) => {
      const card = store.cards[cardId];
      if (!card) return;
      const text = card.transcript || card.preview;
      const utterance = speakText(text);
      if (!utterance) {
        void store.speakCard(card);
        return;
      }
      setPlayingId(cardId);
      utterance.onend = () => setPlayingId(null);
      utterance.onerror = () => setPlayingId(null);
      window.speechSynthesis.speak(utterance);
      void store.speakCard(card).catch(() => undefined);
    },
    [store, speakText],
  );

  const handleReply = useCallback(
    async (cardId: string) => {
      const card = store.cards[cardId];
      if (!card) return;
      setReplyingId(cardId);
      setNotice(null);
      try {
        const text = await recordAndTranscribe();
        if (!text.trim()) {
          setNotice("Não consegui reconhecer a fala. Tente novamente.");
          return;
        }
        await store.replyWithText(cardId, text);
        setNotice(`Resposta enviada para ${card.contact}: “${text}”`);
      } catch (err) {
        setNotice(err instanceof Error ? err.message : "Falha no envio da resposta");
      } finally {
        setReplyingId(null);
      }
    },
    [store, recordAndTranscribe],
  );

  const whatsapp = store.whatsapp?.status ?? "starting";

  return (
    <div className="dashboard">
      <header className="dashboard__topbar window__titlebar">
        <div className="dashboard__brand">
          <span aria-hidden="true">📞</span> <strong>Shortcut</strong> — Kanban
        </div>
        <div className="dashboard__tools">
          <StatusBadge status={whatsapp} />
          {store.flow?.active && <span className="pill pill--live">esteira ativa</span>}
          <RetroButton variant="ghost" icon="🔄" onClick={() => void store.refreshInbox()}>
            Ler caixa
          </RetroButton>
          <RetroButton variant="ghost" icon="🏠" onClick={() => onNavigate("home")}>
            Início
          </RetroButton>
        </div>
      </header>

      {store.error && <p className="alert alert--error">{store.error}</p>}
      {recorderError && <p className="alert alert--error">{recorderError}</p>}
      {notice && <p className="alert alert--info">{notice}</p>}
      {recording && <p className="alert alert--info">🎙 Gravando sua resposta…</p>}

      {store.loading ? (
        <p className="dashboard__loading">Carregando quadro…</p>
      ) : (
        <KanbanBoard
          store={store}
          playingId={playingId}
          replyingId={replyingId}
          onPlay={handlePlay}
          onReply={(cardId) => void handleReply(cardId)}
        />
      )}
    </div>
  );
}
