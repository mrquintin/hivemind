import { useState, FormEvent } from "react";
import { login } from "../api/client";

interface LoginProps {
  onSuccess: () => void;
}

export default function Login({ onSuccess }: LoginProps) {
  const [username, setUsername] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = username.trim();
    if (!trimmed) return;

    setLoading(true);
    setError("");
    try {
      await login(trimmed);
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("403")) {
        setError("Username is not cleared for access.");
      } else if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        setError("Cannot reach server. Check your connection.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "#0a0c10",
        fontFamily: "'SF Mono', 'Consolas', monospace",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#161a24",
          border: "1px solid #2a303d",
          borderRadius: 12,
          padding: "48px 40px",
          width: 380,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            color: "#4ade80",
            marginBottom: 4,
          }}
        >
          HIVEMIND
        </div>
        <div
          style={{
            fontSize: 12,
            color: "#6b7280",
            marginBottom: 32,
            textTransform: "uppercase",
            letterSpacing: 1,
          }}
        >
          Admin Console
        </div>

        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          disabled={loading}
          autoFocus
          style={{
            width: "100%",
            padding: "12px 16px",
            background: "#0a0c10",
            border: "1px solid #2a303d",
            borderRadius: 8,
            color: "#e8ecf2",
            fontSize: 14,
            fontFamily: "inherit",
            outline: "none",
            marginBottom: 16,
            boxSizing: "border-box",
          }}
        />

        <button
          type="submit"
          disabled={loading || !username.trim()}
          style={{
            width: "100%",
            padding: "12px 0",
            background: loading ? "#1c6e3a" : "#22c55e",
            color: "#0a0c10",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            fontFamily: "inherit",
            cursor: loading ? "wait" : "pointer",
            opacity: !username.trim() ? 0.5 : 1,
          }}
        >
          {loading ? "Connecting..." : "Connect"}
        </button>

        {error && (
          <div
            style={{
              marginTop: 16,
              padding: "10px 14px",
              background: "#ef444420",
              border: "1px solid #ef4444",
              borderRadius: 8,
              color: "#fca5a5",
              fontSize: 12,
              textAlign: "left",
            }}
          >
            {error}
          </div>
        )}
      </form>
    </div>
  );
}
