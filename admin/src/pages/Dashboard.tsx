import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type ServiceStatus = {
  postgres: boolean;
  qdrant: boolean;
  server: boolean;
};

const defaultStatus: ServiceStatus = {
  postgres: false,
  qdrant: false,
  server: false,
};

export default function Dashboard() {
  const [status, setStatus] = useState<ServiceStatus>(defaultStatus);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allRunning = status.postgres && status.qdrant && status.server;

  const refresh = async () => {
    try {
      const data = await invoke<ServiceStatus>("get_local_status");
      setStatus(data);
    } catch (err) {
      setError("Unable to read local server status.");
    }
  };

  const toggleServices = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = allRunning
        ? await invoke<ServiceStatus>("stop_local_services")
        : await invoke<ServiceStatus>("start_local_services");
      setStatus(data);
    } catch (err) {
      setError("Unable to update local server status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Local server control and status</p>
      </header>

      <div className="page-content">
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Local Stack Status</h2>
            <div className="button-group">
              <button
                className="btn btn-secondary"
                onClick={refresh}
                disabled={loading}
              >
                Refresh
              </button>
              <button
                className="btn btn-primary"
                onClick={toggleServices}
                disabled={loading}
              >
                {allRunning ? "Stop Stack" : "Start Stack"}
              </button>
            </div>
          </div>

          <div className="status-grid">
            <div className="status-item">
              <span className="status-name">PostgreSQL</span>
              <span
                className={`status-badge ${status.postgres ? "running" : "stopped"}`}
              >
                {status.postgres ? "Running" : "Stopped"}
              </span>
            </div>
            <div className="status-item">
              <span className="status-name">Qdrant Vector DB</span>
              <span
                className={`status-badge ${status.qdrant ? "running" : "stopped"}`}
              >
                {status.qdrant ? "Running" : "Stopped"}
              </span>
            </div>
            <div className="status-item">
              <span className="status-name">Hivemind Cloud API</span>
              <span
                className={`status-badge ${status.server ? "running" : "stopped"}`}
              >
                {status.server ? "Running" : "Stopped"}
              </span>
            </div>
          </div>

          {error && <div className="error-message">{error}</div>}
        </div>

        <div className="card">
          <h2 className="card-title">What This Controls</h2>
          <ul className="info-list">
            <li>
              <strong>PostgreSQL</strong> stores all agent, client, and analysis
              data.
            </li>
            <li>
              <strong>Qdrant</strong> powers knowledge retrieval and similarity
              search.
            </li>
            <li>
              <strong>Cloud API</strong> runs AI analysis and streams results.
            </li>
          </ul>
          <p className="hint">
            Tip: Use this mode when you want a single double-click installer
            that runs the whole stack without separate servers.
          </p>
        </div>
      </div>
    </div>
  );
}
