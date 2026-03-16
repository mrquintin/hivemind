import { useEffect, useState } from "react";
import {
  setApiKey,
  getApiKeyStatus,
  getApiUrl,
  getDefaultApiUrl,
  isCustomServerUrl,
  clearServerUrl,
  checkServerHealth,
} from "../api/client";
import { useConnection } from "../contexts/ConnectionContext";

export default function Settings() {
  const [apiKey, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Current key status
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [keySource, setKeySource] = useState<string | null>(null);
  const [keyMasked, setKeyMasked] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  // Server URL
  const [serverUrl, setServerUrlInput] = useState(getApiUrl());
  const [connecting, setConnecting] = useState(false);
  const [serverStatus, setServerStatus] = useState<
    "idle" | "checking" | "connected" | "failed"
  >("idle");
  const { refreshNow } = useConnection();

  const loadKeyStatus = async () => {
    setLoadingStatus(true);
    try {
      const status = await getApiKeyStatus();
      setKeyConfigured(status.configured);
      setKeySource(status.source);
      setKeyMasked(status.masked);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load API key status"
      );
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    loadKeyStatus();
  }, []);

  const handleSave = async () => {
    if (!apiKey.trim()) {
      setError("API key is required");
      return;
    }
    if (!apiKey.trim().startsWith("sk-")) {
      setError("Invalid API key format — must start with sk-");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await setApiKey(apiKey.trim());
      setSuccess("API key saved successfully");
      setApiKeyInput("");
      await loadKeyStatus();
      setTimeout(() => setSuccess(null), 4000);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save API key"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleConnect = async () => {
    const url = serverUrl.trim();
    if (!url) {
      setError("Server URL is required");
      return;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setError("URL must start with http:// or https://");
      return;
    }

    setConnecting(true);
    setServerStatus("checking");
    setError(null);
    setSuccess(null);

    const result = await checkServerHealth({
      candidateUrl: url,
      includeLocalFallback: false,
      persistSuccess: true,
    });

    if (result.connected) {
      setServerStatus("connected");
      setServerUrlInput(result.url || url);
      setSuccess("Connected to server successfully");
      refreshNow();
      // Reload API key status from the new server
      await loadKeyStatus();
      setTimeout(() => setSuccess(null), 4000);
    } else {
      setServerStatus("failed");
      setError(
        `Could not connect to ${url}. Make sure the cloud server is running and accessible.`
      );
    }
    setConnecting(false);
  };

  const handleReset = () => {
    clearServerUrl();
    setServerUrlInput(getApiUrl());
    setServerStatus("idle");
    setSuccess("Reset to default server URL");
    refreshNow();
    loadKeyStatus();
    setTimeout(() => setSuccess(null), 4000);
  };

  const sourceLabel: Record<string, string> = {
    settings_file: "Settings file (encrypted)",
    environment: "Environment variable",
    encrypted_store: "Encrypted store",
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Configure server connection and API keys
          </p>
        </div>
      </header>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      <div className="page-content">
        {/* Server Connection */}
        <div className="card">
          <h2 className="card-title">Server Connection</h2>
          <p className="card-subtitle">
            Connect to the Hivemind cloud server. Enter the server's address if
            it's running on a different machine.
          </p>

          <div className="settings-status">
            <div className="settings-status-row">
              <span className="settings-label">Status</span>
              <span
                className={`settings-value ${
                  serverStatus === "connected"
                    ? "configured"
                    : serverStatus === "failed"
                    ? "not-configured"
                    : ""
                }`}
              >
                {serverStatus === "checking"
                  ? "Connecting..."
                  : serverStatus === "connected"
                  ? "Connected"
                  : serverStatus === "failed"
                  ? "Connection failed"
                  : "—"}
              </span>
            </div>
            {isCustomServerUrl() && (
              <div className="settings-status-row">
                <span className="settings-label">Default</span>
                <span className="settings-value mono muted">
                  {getDefaultApiUrl()}
                </span>
              </div>
            )}
          </div>

          <div className="settings-form">
            <div className="form-group">
              <label className="form-label">Server URL</label>
              <input
                type="text"
                className="form-input"
                value={serverUrl}
                onChange={(e) => setServerUrlInput(e.target.value)}
                placeholder="https://api.yourdomain.com"
                onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              />
              <span className="form-hint">
                Enter the cloud server's address (e.g.,
                https://api.yourdomain.com or http://YOUR_EC2_PUBLIC_IP:8000).
              </span>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <button
                className="btn btn-primary"
                onClick={handleConnect}
                disabled={connecting || !serverUrl.trim()}
              >
                {connecting ? "Connecting..." : "Connect"}
              </button>
              {isCustomServerUrl() && (
                <button
                  className="btn btn-secondary"
                  onClick={handleReset}
                  style={{ opacity: 0.8 }}
                >
                  Reset to Default
                </button>
              )}
            </div>
          </div>
        </div>

        {/* API Key Configuration */}
        <div className="card">
          <h2 className="card-title">Anthropic API Key</h2>
          <p className="card-subtitle">
            Required for AI unit functionality. The key is stored encrypted on
            the cloud server and used for all LLM calls including document
            optimization and agent analysis.
          </p>

          {/* Current status */}
          <div className="settings-status">
            <div className="settings-status-row">
              <span className="settings-label">Status</span>
              {loadingStatus ? (
                <span className="settings-value muted">Checking...</span>
              ) : keyConfigured ? (
                <span className="settings-value configured">Configured</span>
              ) : (
                <span className="settings-value not-configured">
                  Not configured
                </span>
              )}
            </div>
            {keyConfigured && keySource && (
              <div className="settings-status-row">
                <span className="settings-label">Source</span>
                <span className="settings-value">
                  {sourceLabel[keySource] || keySource}
                </span>
              </div>
            )}
            {keyConfigured && keyMasked && (
              <div className="settings-status-row">
                <span className="settings-label">Key</span>
                <span className="settings-value mono">{keyMasked}</span>
              </div>
            )}
          </div>

          {/* Set / update key */}
          <div className="settings-form">
            <div className="form-group">
              <label className="form-label">
                {keyConfigured ? "Update API Key" : "Enter API Key"}
              </label>
              <input
                type="password"
                className="form-input"
                value={apiKey}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="sk-ant-..."
                autoComplete="off"
              />
              <span className="form-hint">
                Your Anthropic API key. Starts with sk-ant- or sk-. The key
                is encrypted before being stored on the server.
              </span>
            </div>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving || !apiKey.trim()}
            >
              {saving ? "Saving..." : keyConfigured ? "Update Key" : "Save Key"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
