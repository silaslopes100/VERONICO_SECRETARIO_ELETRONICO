export type ColumnId = "new" | "heard" | "waiting_reply" | "responded";

export type WhatsAppStatusId = "starting" | "waiting_qr" | "connected" | "error" | "stopped";

export interface Card {
  id: string;
  chatId: string;
  contact: string;
  preview: string;
  timestamp: string;
  column: ColumnId;
  transcript: string;
  replyText: string;
  isAudio: boolean;
  unreadCount: number;
  createdAt: number;
  updatedAt: number;
  archived: boolean;
}

export interface Column {
  id: ColumnId;
  title: string;
  cardIds: string[];
}

export interface KanbanState {
  columns: Column[];
  cards: Record<string, Card>;
  unreadCount: number;
  updatedAt: number;
}

export interface WhatsAppStatus {
  status: WhatsAppStatusId;
  last_error: string | null;
  headless: boolean;
}

export interface FlowStatus {
  active: boolean;
  currentCardId: string | null;
  currentContact: string | null;
  lastCommand: string;
  whatsapp: string;
}

export interface StatusResponse {
  whatsapp: WhatsAppStatus;
  flow: FlowStatus;
  unread: number;
}

export type WsEvent =
  | { type: "kanban_state"; payload: KanbanState }
  | { type: "whatsapp_status"; payload: WhatsAppStatus }
  | { type: "flow_status"; payload: FlowStatus };

export interface MoveResult {
  column: ColumnId;
}

export interface TranscribeResult {
  text: string;
}

export interface ReplyResult {
  sent: boolean;
  transcript: string;
  card: Card | null;
}

export type PageView = "home" | "dashboard";
