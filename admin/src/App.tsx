import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import TheoryFrameworks from "./pages/TheoryFrameworks";
import Simulations from "./pages/Simulations";
import PracticalityUnits from "./pages/PracticalityUnits";
import Settings from "./pages/Settings";
import { ConnectionProvider, useConnection } from "./contexts/ConnectionContext";

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

function AppContent() {
  const { status } = useConnection();

  return (
    <div className="app-layout" style={{ marginTop: status !== "connected" ? "48px" : 0 }}>
      <ConnectionBanner />
      <Sidebar />
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
  return (
    <ConnectionProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ConnectionProvider>
  );
}
