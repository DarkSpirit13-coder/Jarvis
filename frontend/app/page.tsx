/** Primary operational dashboard for JARVIS. */
import { ChatConsole } from "@/components/chat-console";
import { StatusPanel } from "@/components/status-panel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-6 py-8">
        <header className="flex items-center justify-between border-b border-zinc-800 pb-5">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-cyan-300">AI Operating System</p>
            <h1 className="mt-2 text-4xl font-semibold tracking-normal">JARVIS</h1>
          </div>
          <div className="rounded-md border border-zinc-700 px-3 py-2 text-sm text-zinc-300">Production Console</div>
        </header>
        <div className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
          <ChatConsole />
          <StatusPanel />
        </div>
      </section>
    </main>
  );
}
