import { NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import { checkServerHealth, getApiUrl, pingServer, logout } from "../api/client";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "◉" },
  { path: "/theory", label: "Theory Frameworks", icon: "▣" },
  { path: "/simulations", label: "Simulations", icon: "◇" },
  { path: "/practicality", label: "Practicality Units", icon: "◈" },
  { path: "/settings", label: "Settings", icon: "⚙" },
];

type ConnectionStatus = "checking" | "connected" | "disconnected";
type PingStatus = "idle" | "pinging" | "success" | "error";

interface SidebarProps {
  onLogout: () => void;
}

export default function Sidebar({ onLogout }: SidebarProps) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("checking");
  const [pingStatus, setPingStatus] = useState<PingStatus>("idle");

  useEffect(() => {
    const checkConnection = async () => {
      const result = await checkServerHealth();
      setConnectionStatus(result.connected ? "connected" : "disconnected");
    };

    // Check immediately
    checkConnection();

    // Check every 30 seconds
    const interval = setInterval(checkConnection, 30000);
    return () => clearInterval(interval);
  }, []);

  const handlePing = async () => {
    setPingStatus("pinging");
    try {
      await pingServer();
      setPingStatus("success");
      // Reset after 2 seconds
      setTimeout(() => setPingStatus("idle"), 2000);
    } catch {
      setPingStatus("error");
      setTimeout(() => setPingStatus("idle"), 2000);
    }
  };

  const handleLogout = () => {
    logout();
    onLogout();
  };

  const statusColor = {
    checking: "#f59e0b",
    connected: "#22c55e",
    disconnected: "#ef4444",
  }[connectionStatus];

  const statusText = {
    checking: "Checking...",
    connected: "Connected",
    disconnected: "Disconnected",
  }[connectionStatus];

  const pingButtonText = {
    idle: "Test Connection",
    pinging: "Pinging...",
    success: "✓ Success!",
    error: "✗ Failed",
  }[pingStatus];

  const pingButtonColor = {
    idle: "var(--primary)",
    pinging: "var(--warn)",
    success: "var(--success)",
    error: "var(--danger)",
  }[pingStatus];

  return (
    <nav className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">HIVEMIND</div>
        <div className="sidebar-subtitle">Admin Console</div>
      </div>
      <ul className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <li key={item.path}>
            <NavLink
              to={item.path}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? "active" : ""}`
              }
              end={item.path === "/"}
            >
              <span className="sidebar-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="sidebar-footer">
        <div className="connection-status" title={getApiUrl()}>
          <span
            className="status-dot"
            style={{ backgroundColor: statusColor }}
          />
          <span className="status-text">{statusText}</span>
        </div>
        <button
          className="ping-button"
          onClick={handlePing}
          disabled={pingStatus === "pinging" || connectionStatus !== "connected"}
          style={{
            backgroundColor: pingButtonColor,
            opacity: connectionStatus !== "connected" ? 0.5 : 1,
          }}
        >
          {pingButtonText}
        </button>
        <button
          className="ping-button"
          onClick={handleLogout}
          style={{
            backgroundColor: "transparent",
            border: "1px solid #2a303d",
            color: "#9aa4b8",
            marginTop: 4,
          }}
        >
          Logout
        </button>
        <div className="version-label">v0.1.0</div>
      </div>
    </nav>
  );
}
