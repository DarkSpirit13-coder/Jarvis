/** Backend health status panel. */
"use client";

import { useEffect, useState } from "react";
import { fetchHealth } from "@/lib/api";
import type { HealthResponse } from "@/types/api";

export function StatusPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchHealth()
      .then((result) => {
        if (mounted) setHealth(result);
      })
      .catch((reason: Error) => {
        if (mounted) setError(reason.message);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <aside className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
      <h2 className="text-xl font-medium">System Health</h2>
      <dl className="mt-5 space-y-3 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">API</dt>
          <dd className="font-medium text-cyan-200">{health?.status ?? (error ? "unavailable" : "checking")}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">Version</dt>
          <dd className="text-zinc-200">{health?.version ?? "unknown"}</dd>
        </div>
      </dl>
      {error ? <p className="mt-4 text-sm text-red-300">{error}</p> : null}
    </aside>
  );
}
