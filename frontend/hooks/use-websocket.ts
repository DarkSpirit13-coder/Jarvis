/** React hook for managing a JARVIS conversation WebSocket. */
"use client";

import { useEffect, useRef, useState } from "react";

export function useConversationSocket(conversationId: string) {
  const socketRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";
    const socket = new WebSocket(`${baseUrl}/conversations/${conversationId}`);
    socketRef.current = socket;
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    return () => socket.close();
  }, [conversationId]);

  return { connected, socket: socketRef.current };
}
