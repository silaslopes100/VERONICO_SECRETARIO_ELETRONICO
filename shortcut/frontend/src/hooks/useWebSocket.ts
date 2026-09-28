import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../services/api";
import type { WsEvent } from "../types";

interface WebSocketState {
  connected: boolean;
  lastEvent: WsEvent | null;
}

const RETRY_MIN_MS = 1000;
const RETRY_MAX_MS = 10000;

/**
 * Conecta ao WebSocket do backend com reconexão em backoff exponencial
 * (1s → 10s) e repassa cada evento recebido para o handler informado.
 *
 * O cleanup marca a instância como fechada antes de encerrar o socket, o que
 * evita a "corrida" do React StrictMode (montagem dupla em dev) gerar
 * conexões/zumbis — causa de erros `ECONNABORTED` no proxy do Vite.
 */
export function useWebSocket(onEvent: (event: WsEvent) => void): WebSocketState {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let retryDelay = RETRY_MIN_MS;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      try {
        socket = new WebSocket(wsUrl());
      } catch {
        scheduleRetry();
        return;
      }

      socket.onopen = () => {
        retryDelay = RETRY_MIN_MS;
        if (!disposed) setConnected(true);
      };

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as WsEvent;
          setLastEvent(event);
          handlerRef.current(event);
        } catch {
          /* ignora frames inválidos */
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (!disposed) scheduleRetry();
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    const scheduleRetry = () => {
      if (disposed || retryTimer !== undefined) return;
      retryTimer = window.setTimeout(() => {
        retryTimer = undefined;
        retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
        connect();
      }, retryDelay);
    };

    connect();

    return () => {
      disposed = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      const current = socket;
      socket = null;
      current?.close();
    };
  }, []);

  return { connected, lastEvent };
}
