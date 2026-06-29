/** Typed HTTP client helpers for the JARVIS backend. */
import type { HealthResponse } from "@/types/api";
import type { ChatMessage } from "@/types/chat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }
  return response.json() as Promise<HealthResponse>;
}

export async function streamChat(
  message: string,
  conversationId: string,
  onToken: (token: string) => void,
): Promise<void> {
  /** Stream a chat turn from the backend SSE endpoint. */
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId, user_id: "frontend" }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed with status ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const line = event.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const data = line.replace("data: ", "");
      if (data === "[DONE]") return;
      const parsed = JSON.parse(data) as { token: string };
      onToken(parsed.token);
    }
  }
}

export function createMessage(role: ChatMessage["role"], content: string): ChatMessage {
  /** Create a client-side chat message with a stable unique id. */
  return { id: crypto.randomUUID(), role, content };
}
