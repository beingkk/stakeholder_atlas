import { useEffect, useState } from "react";

import { fetchApiStatus, fetchHealth } from "./lib/api";
import "./App.css";

type StatusState =
  | { kind: "loading" }
  | { kind: "ready"; health: { status: string; version: string }; api: { status: string } }
  | { kind: "error"; message: string };

export default function App() {
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function loadStatus() {
      try {
        const [health, api] = await Promise.all([fetchHealth(), fetchApiStatus()]);
        if (!cancelled) {
          setStatus({ kind: "ready", health, api });
        }
      } catch (error) {
        if (!cancelled) {
          setStatus({
            kind: "error",
            message: error instanceof Error ? error.message : "Unknown error",
          });
        }
      }
    }

    void loadStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app">
      <h1>Stakeholder Atlas</h1>
      <p>Minimal React + FastAPI scaffold.</p>

      {status.kind === "loading" && (
        <section className="status-card">
          <h2>Backend status</h2>
          <p>Checking API connectivity…</p>
        </section>
      )}

      {status.kind === "ready" && (
        <section className="status-card">
          <h2>Backend status</h2>
          <dl>
            <dt>Health</dt>
            <dd>{status.health.status}</dd>
            <dt>Version</dt>
            <dd>{status.health.version}</dd>
            <dt>API</dt>
            <dd>{status.api.status}</dd>
          </dl>
        </section>
      )}

      {status.kind === "error" && (
        <section className="status-card error">
          <h2>Backend status</h2>
          <p>{status.message}</p>
        </section>
      )}
    </main>
  );
}
