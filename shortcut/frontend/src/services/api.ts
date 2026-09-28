import type {
  ColumnId,
  KanbanState,
  ReplyResult,
  StatusResponse,
  TranscribeResult,
} from "../types";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export const api = {
  getStatus: () => request<StatusResponse>("/api/status"),
  getState: () => request<KanbanState>("/api/state"),
  refreshInbox: () => request<{ newCards: number }>("/api/refresh", { method: "POST" }),

  moveCard: (cardId: string, column: ColumnId) =>
    request(`/api/cards/${cardId}/move`, {
      method: "POST",
      body: JSON.stringify({ column }),
    }),

  archiveCard: (cardId: string) =>
    request<{ archived: boolean }>(`/api/cards/${cardId}/archive`, { method: "POST" }),

  speak: (text: string) =>
    request<{ spoken: boolean }>("/api/voice/speak", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  listen: (seconds = 6) =>
    request<{ text: string }>("/api/voice/listen", {
      method: "POST",
      body: JSON.stringify({ seconds }),
    }),

  transcribeAudio: async (blob: Blob): Promise<TranscribeResult> => {
    const form = new FormData();
    form.append("file", blob, "reply.webm");
    const response = await fetch(`${BASE}/api/voice/transcribe`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) throw new Error(`Transcrição falhou: ${response.status}`);
    return (await response.json()) as TranscribeResult;
  },

  replyByVoice: (cardId: string) =>
    request<ReplyResult>("/api/voice/reply", {
      method: "POST",
      body: JSON.stringify({ cardId }),
    }),

  replyWithText: (cardId: string, text: string) =>
    request<ReplyResult>(`/api/cards/${cardId}/reply-text`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  announceUnread: () =>
    request<{ message: string }>("/api/voice/announce", { method: "POST" }),

  startFlow: () => request("/api/voice/flow/start", { method: "POST" }),
  stopFlow: () => request("/api/voice/flow/stop", { method: "POST" }),
  flowStatus: () => request("/api/voice/flow/status"),
};

export function wsUrl(): string {
  if (BASE) return BASE.replace(/^http/, "ws") + "/ws";
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws`;
}
