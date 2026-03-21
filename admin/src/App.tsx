import { useState, useEffect, useCallback } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import TheoryFrameworks from "./pages/TheoryFrameworks";
import Simulations from "./pages/Simulations";
import PracticalityUnits from "./pages/PracticalityUnits";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import { ConnectionProvider, useConnection } from "./contexts/ConnectionContext";
import { getAuthToken, logout, getApiKeyStatus } from "./api/client";

function ConnectionBanner() {
  const { status, retryCount } = useConnection();

  if (status === "connected") {
    return null;
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        padding: "12px 20px",
        backgroundColor: status === "checking" ? "#f59e0b" : "#ef4444",
        color: "white",
        textAlign: "center",
        zIndex: 9999,
        fontWeight: 500,
      }}
    >
      {status === "checking" ? (
        <>Connecting to Hivemind Cloud Server...</>
      ) : (
        <>
          Unable to connect to server. Retrying... (attempt {retryCount})
        </>
      )}
    </div>
  );
}

function AppContent({ onLogout }: { onLogout: () => void }) {
  const { status } = useConnection();

  return (
    <div className="app-layout" style={{ marginTop: status !== "connected" ? "48px" : 0 }}>
      <ConnectionBanner />
      <Sidebar onLogout={onLogout} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/theory" element={<TheoryFrameworks />} />
          <Route path="/simulations" element={<Simulations />} />
          <Route path="/practicality" element={<PracticalityUnits />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);

  // On mount, try to restore session from stored token
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setChecking(false);
      return;
    }
    // Validate the token with a lightweight authenticated request
    getApiKeyStatus()
      .then(() => setAuthenticated(true))
      .catch(() => {
        logout(); // Token expired or invalid — clear it
      })
      .finally(() => setChecking(false));
  }, []);

  const handleLogout = useCallback(() => {
    logout();
    setAuthenticated(false);
  }, []);

  // Show nothing while checking stored token
  if (checking) {
    return null;
  }

  if (!authenticated) {
    return <Login onSuccess={() => setAuthenticated(true)} />;
  }

  return (
    <ConnectionProvider>
      <BrowserRouter>
        <AppContent onLogout={handleLogout} />
      </BrowserRouter>
    </ConnectionProvider>
  );
}
