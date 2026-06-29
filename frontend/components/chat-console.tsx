/** Streaming chat console for JARVIS. */
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { createMessage, streamChat } from "@/lib/api";
import type { ChatMessage } from "@/types/chat";

export function ChatConsole() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    createMessage("system", "JARVIS intelligence layer online. Ask for analysis, tool use, or memory-aware help."),
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const conversationId = "web-console";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;
    const assistant = createMessage("assistant", "");
    setMessages((current) => [...current, createMessage("user", text), assistant]);
    setInput("");
    setThinking(true);
    try {
      await streamChat(text, conversationId, (token) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistant.id ? { ...message, content: message.content + token } : message,
          ),
        );
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Streaming failed";
      setMessages((current) =>
        current.map((item) => (item.id === assistant.id ? { ...item, content: `Error: ${message}` } : item)),
      );
    } finally {
      setThinking(false);
    }
  }

  return (
    <section className="flex min-h-[640px] flex-col rounded-lg border border-zinc-800 bg-zinc-900">
      <div className="border-b border-zinc-800 px-5 py-4">
        <h2 className="text-lg font-medium">Conversation</h2>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {messages.map((message) => (
          <article
            key={message.id}
            className={`rounded-md border px-4 py-3 ${
              message.role === "user"
                ? "ml-auto max-w-[85%] border-cyan-800 bg-cyan-950/40"
                : "mr-auto max-w-[92%] border-zinc-800 bg-zinc-950"
            }`}
          >
            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-zinc-500">{message.role}</div>
            <div className="prose prose-invert max-w-none prose-p:my-2 prose-pre:bg-zinc-900">
              <ReactMarkdown>{message.content || (thinking ? "Thinking..." : "")}</ReactMarkdown>
            </div>
          </article>
        ))}
        {thinking ? <div className="text-sm text-cyan-200">JARVIS is thinking...</div> : null}
        <div ref={bottomRef} />
      </div>
      <form className="flex gap-3 border-t border-zinc-800 p-4" onSubmit={submit}>
        <input
          className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none focus:border-cyan-400"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          aria-label="Message JARVIS"
        />
        <button
          className="rounded-md bg-cyan-300 px-5 py-3 text-sm font-semibold text-zinc-950 disabled:cursor-not-allowed disabled:opacity-60"
          type="submit"
          disabled={thinking}
        >
          Send
        </button>
      </form>
    </section>
  );
}
