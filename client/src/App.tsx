import { useState, useEffect, useRef, useCallback } from "react";
import "./styles.css";
import {
  enterSystem,
  logout,
  listPublishedAgents,
  checkServerHealth,
  getAuthToken,
  startAnalysisStreaming,
  getApiUrl,
  setServerUrl,
  clearServerUrl,
  isCustomServerUrl,
  type Agent,
  type AnalysisRequest,
  type AnalysisResult,
  type StreamEvent,
  type Recommendation,
  getDensityBounds,
  getMe,
  listClientData,
  createClientData,
  deleteClientData,
  uploadClientData,
  type ClientDataEntry,
  listScrapedSources,
  createScrapedSource,
  triggerScrape,
  deleteScrapedSource,
  type ScrapedSource,
} from "./api/client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Phase = "login" | "login_fade_out" | "main" | "analysis" | "output";

type AnalysisStep =
  | "initializing"
  | "theory_analyzing"
  | "monitor_aggregating"
  | "pass_to_practicality"
  | "practicality_voting"
  | "repairing"
  | "veto"
  | "done";

type ConnectionStatus = "connected" | "connecting" | "disconnected";

// ---------------------------------------------------------------------------
// SliderWithInput (reusable)
// ---------------------------------------------------------------------------

function SliderWithInput({
  label,
  value,
  min,
  max,
  step,
  minLabel,
  maxLabel,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  minLabel: string;
  maxLabel: string;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <div className="slider-block">
      <div className="slider-top">
        <span className="slider-label">{label}</span>
        <input
          type="number"
          className="slider-number"
          value={value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (n >= min && n <= max) onChange(n);
          }}
        />
      </div>
      <input
        type="range"
        className="slider-range"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div className="slider-extremes">
        <span>{minLabel}</span>
        <span>{maxLabel}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LoginScreen
// ---------------------------------------------------------------------------

function LoginScreen({
  username,
  onUsernameChange,
  password,
  onPasswordChange,
  onSubmit,
  error,
  isLoading,
  connectionStatus,
  onServerUrlChange,
}: {
  username: string;
  onUsernameChange: (v: string) => void;
  password: string;
  onPasswordChange: (v: string) => void;
  onSubmit: () => void;
  error: string;
  isLoading: boolean;
  connectionStatus: ConnectionStatus;
  onServerUrlChange: () => void;
}) {
  const [splashDone, setSplashDone] = useState(false);
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [serverUrlInput, setServerUrlInput] = useState(getApiUrl());
  const [urlError, setUrlError] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setSplashDone(true), 1800);
    return () => clearTimeout(timer);
  }, []);

  const handleServerConnect = () => {
    const url = serverUrlInput.trim();
    if (!url) { setUrlError("URL is required"); return; }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setUrlError("URL must start with http:// or https://");
      return;
    }
    setUrlError("");
    setServerUrl(url);
    onServerUrlChange();
  };

  const handleServerReset = () => {
    clearServerUrl();
    setServerUrlInput(getApiUrl());
    setUrlError("");
    onServerUrlChange();
  };

  return (
    <div className="login-screen">
      <div className={`login-splash-wrapper ${splashDone ? "lifted" : ""}`}>
        <img
          src="/hivemind-logo.png"
          alt="Hivemind"
          className="login-logo"
          draggable={false}
        />
      </div>

      <div className={`login-form-wrapper ${splashDone ? "visible" : ""}`}>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          <label className="login-label">Username</label>
          <input
            className="login-input"
            type="text"
            placeholder="Enter your username"
            value={username}
            onChange={(e) => onUsernameChange(e.target.value)}
            autoFocus
          />
          <label className="login-label" style={{ marginTop: 8 }}>Password</label>
          <input
            className="login-input"
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
          />
          {error && <div className="login-error">{error}</div>}
          <button
            className="login-button"
            type="submit"
            disabled={!username.trim() || !password || isLoading}
          >
            {isLoading ? "Verifying..." : "Enter"}
          </button>
          <div className="login-connection">
            <span
              className={`connection-dot ${connectionStatus}`}
            />
            <span>
              {connectionStatus === "connected"
                ? "Server connected"
                : connectionStatus === "connecting"
                ? "Connecting..."
                : "Server offline"}
            </span>
            <button
              type="button"
              className="server-config-toggle"
              onClick={() => setShowServerConfig(!showServerConfig)}
              title="Server settings"
            >
              {showServerConfig ? "Hide" : "Configure"}
            </button>
          </div>

          {showServerConfig && (
            <div className="server-config">
              <label className="login-label" style={{ fontSize: "0.75rem", marginTop: "8px" }}>
                Server URL
              </label>
              <input
                className="login-input"
                type="text"
                placeholder="http://13.63.209.56:8000"
                value={serverUrlInput}
                onChange={(e) => setServerUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleServerConnect())}
                style={{ fontSize: "0.85rem" }}
              />
              {urlError && <div className="login-error" style={{ fontSize: "0.75rem" }}>{urlError}</div>}
              <div style={{ display: "flex", gap: "6px", marginTop: "6px" }}>
                <button
                  type="button"
                  className="login-button"
                  style={{ padding: "6px 12px", fontSize: "0.8rem" }}
                  onClick={handleServerConnect}
                >
                  Connect
                </button>
                {isCustomServerUrl() && (
                  <button
                    type="button"
                    className="login-button"
                    style={{ padding: "6px 12px", fontSize: "0.8rem", opacity: 0.7 }}
                    onClick={handleServerReset}
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LoginFadeOut
// ---------------------------------------------------------------------------

function LoginFadeOut({
  username,
  onDone,
}: {
  username: string;
  onDone: () => void;
}) {
  const [overlayActive, setOverlayActive] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setOverlayActive(true));
    const timer = setTimeout(onDone, 2200);
    return () => clearTimeout(timer);
  }, [onDone]);

  return (
    <div className="login-fade-out">
      <div className="login-screen">
        <div className="login-splash-wrapper lifted">
          <img src="/hivemind-logo.png" alt="Hivemind" className="login-logo" draggable={false} />
        </div>
        <div className="login-form-wrapper visible">
          <div className="login-form">
            <label className="login-label">Username</label>
            <input className="login-input" type="text" value={username} readOnly />
          </div>
        </div>
      </div>
      <div className={`login-fade-overlay ${overlayActive ? "active" : ""}`} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  // --- Phase ---
  const [phase, setPhase] = useState<Phase>("login");

  // --- Auth ---
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // --- Connection ---
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const healthRef = useRef<ReturnType<typeof setTimeout>>();
  const retryCountRef = useRef(0);

  // --- Agents ---
  const [agents, setAgents] = useState<Agent[]>([]);
  const theoryAgents = agents.filter((a) => a.network_type === "theory");
  const practicalityAgents = agents.filter((a) => a.network_type === "practicality");

  // --- Form inputs (primary) ---
  const [problemText, setProblemText] = useState("");
  const [sufficiency, setSufficiency] = useState(2);
  const [feasibility, setFeasibility] = useState(60);
  const [analysisMode, setAnalysisMode] = useState<"simple" | "full">("simple");
  const [effortLevel, setEffortLevel] = useState<"low" | "medium" | "high">("medium");

  // --- Form inputs (advanced / experimental) ---
  const [density, setDensity] = useState(8000);
  const [densityMin, setDensityMin] = useState(1000);
  const [densityMax, setDensityMax] = useState(50000);
  const [densityMode, setDensityMode] = useState(true);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.65);
  const [revisionStrength, setRevisionStrength] = useState(0.5);
  const [practicalityCriticality, setPracticalityCriticality] = useState(0.5);
  const [useCaseProfile, setUseCaseProfile] = useState("");
  const [decisionType, setDecisionType] = useState("");
  const [selectedTheoryIds, setSelectedTheoryIds] = useState<Set<string>>(new Set());
  const [selectedPracticalityIds, setSelectedPracticalityIds] = useState<Set<string>>(new Set());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showDataPanel, setShowDataPanel] = useState(false);
  const [contextText, setContextText] = useState("");
  const [clientId, setClientId] = useState<string | null>(null);
  const [clientDataEntries, setClientDataEntries] = useState<ClientDataEntry[]>([]);
  const [newEntryLabel, setNewEntryLabel] = useState("");
  const [newEntryContent, setNewEntryContent] = useState("");
  const [savingEntry, setSavingEntry] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [scrapedSources, setScrapedSources] = useState<ScrapedSource[]>([]);
  const [newSourceUrl, setNewSourceUrl] = useState("");
  const [sourceMode, setSourceMode] = useState<"url" | "search_query">("url");

  // --- Analysis state ---
  const [analysisStep, setAnalysisStep] = useState<AnalysisStep>("initializing");
  const [runNumber, setRunNumber] = useState(1);
  const [theoryUnitNames, setTheoryUnitNames] = useState<string[]>([]);
  const [completedTheoryAgents, setCompletedTheoryAgents] = useState<Set<string>>(new Set());
  const [activeTheoryAgent, setActiveTheoryAgent] = useState<string | null>(null);
  const [aggregatedCount, setAggregatedCount] = useState(0);
  const [debateRound, setDebateRound] = useState(0);
  const [revisionApplied, setRevisionApplied] = useState(false);
  const [conclusionsDrifting, setConclusionsDrifting] = useState(false);
  const [practicalityScores, setPracticalityScores] = useState<Map<string, number>>(new Map());
  const [votingAgentName, setVotingAgentName] = useState<string | null>(null);
  const [showVeto, setShowVeto] = useState(false);
  const [repairCount, setRepairCount] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [showOutputModal, setShowOutputModal] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // --- Output modal ---
  const [expandedRecs, setExpandedRecs] = useState<Set<string>>(new Set());
  const [showAudit, setShowAudit] = useState(false);

  // ---------------------------------------------------------------------------
  // Health check loop
  // ---------------------------------------------------------------------------

  const runHealthCheck = useCallback(async () => {
    try {
      const result = await checkServerHealth();
      if (result.connected) {
        setConnectionStatus("connected");
        retryCountRef.current = 0;
        healthRef.current = setTimeout(runHealthCheck, 30000);
      } else {
        throw new Error("not connected");
      }
    } catch {
      setConnectionStatus(retryCountRef.current === 0 ? "connecting" : "disconnected");
      retryCountRef.current++;
      const delay = Math.min(2000 + retryCountRef.current * 1000, 5000);
      healthRef.current = setTimeout(runHealthCheck, delay);
    }
  }, []);

  useEffect(() => {
    runHealthCheck();
    return () => {
      if (healthRef.current) clearTimeout(healthRef.current);
    };
  }, [runHealthCheck]);

  // --- Fetch density bounds from server ---
  const fetchDensityBounds = useCallback(async (agentList: Agent[]) => {
    const kbIds = new Set<string>();
    for (const a of agentList) {
      if (a.network_type === "theory") {
        // Agent may have knowledge_base_ids on the full object
        const ids = (a as unknown as { knowledge_base_ids?: string[] }).knowledge_base_ids;
        if (ids) ids.forEach((id) => kbIds.add(id));
      }
    }
    if (kbIds.size === 0) return;
    const bounds = await getDensityBounds(Array.from(kbIds));
    if (bounds && bounds.sum_all_doc_tokens > 0) {
      const min = Math.max(bounds.min_doc_tokens, 500);
      const max = bounds.sum_all_doc_tokens;
      setDensityMin(min);
      setDensityMax(max);
      // Clamp current density to new range
      setDensity((prev) => Math.max(min, Math.min(max, prev)));
    }
  }, []);

  // --- Fetch client identity and saved data ---
  const fetchClientData = useCallback(async () => {
    try {
      const me = await getMe();
      setClientId(me.client_id);
      const [entries, sources] = await Promise.all([
        listClientData(me.client_id),
        listScrapedSources().catch(() => [] as ScrapedSource[]),
      ]);
      setClientDataEntries(entries);
      setScrapedSources(sources);
    } catch {
      // Non-critical — client data panel just stays empty
    }
  }, []);

  // --- Restore session ---
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      listPublishedAgents()
        .then((a) => {
          setAgents(a);
          setUsername("(session restored)");
          setPhase("main");
          fetchDensityBounds(a);
          fetchClientData();
        })
        .catch(() => {
          // Token expired
        });
    }
  }, [fetchDensityBounds, fetchClientData]);

  // ---------------------------------------------------------------------------
  // Login handler
  // ---------------------------------------------------------------------------

  async function handleLogin() {
    if (!username.trim() || !password) return;
    setLoginLoading(true);
    setLoginError("");
    try {
      await enterSystem({ username: username.trim(), password });
      setPassword("");
      setPhase("login_fade_out");
      try {
        const a = await listPublishedAgents();
        setAgents(a);
        fetchDensityBounds(a);
        fetchClientData();
      } catch {
        // Will retry later
      }
    } catch (err: unknown) {
      const msg = (err as Error).message || "";
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("Load failed")) {
        setLoginError("Failed to connect to server");
      } else {
        setLoginError(msg || "Login failed");
      }
    } finally {
      setLoginLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Analysis SSE handler
  // ---------------------------------------------------------------------------

  function handleStartAnalysis() {
    const req: AnalysisRequest = {
      problem_statement: problemText,
      analysis_mode: analysisMode,
      effort_level: effortLevel,
      context_document_texts: [
        ...clientDataEntries.map((e) => e.content).filter(Boolean),
        ...(contextText.trim() ? [contextText.trim()] : []),
      ],
      sufficiency_value: sufficiency,
      feasibility_threshold: feasibility,
      theory_network_density: densityMode ? density : null,
      enabled_theory_agent_ids: densityMode ? [] : Array.from(selectedTheoryIds),
      enabled_practicality_agent_ids: Array.from(selectedPracticalityIds),
      max_veto_restarts: analysisMode === "full" ? 1 : 0,
      similarity_threshold: similarityThreshold,
      revision_strength: revisionStrength,
      practicality_criticality: practicalityCriticality,
      use_case_profile: useCaseProfile || null,
      decision_type: decisionType || null,
    };

    // Reset analysis state
    setAnalysisStep("initializing");
    setRunNumber(1);
    setTheoryUnitNames([]);
    setCompletedTheoryAgents(new Set());
    setActiveTheoryAgent(null);
    setAggregatedCount(0);
    setDebateRound(0);
    setRevisionApplied(false);
    setConclusionsDrifting(false);
    setPracticalityScores(new Map());
    setVotingAgentName(null);
    setShowVeto(false);
    setRepairCount(0);
    setAnalysisResult(null);
    setAnalysisError(null);
    setShowOutputModal(false);
    setExpandedRecs(new Set());
    setShowAudit(false);

    setPhase("analysis");

    const controller = startAnalysisStreaming(
      req,
      (event: StreamEvent) => handleSSEEvent(event),
      (error: string) => {
        setAnalysisError(error);
        setAnalysisStep("done");
      }
    );
    abortRef.current = controller;
  }

  function handleSSEEvent(event: StreamEvent) {
    switch (event.type) {
      case "debate_start":
        setAnalysisStep("theory_analyzing");
        break;

      case "units_created":
        break;

      case "initial_solutions_start":
        setAnalysisStep("theory_analyzing");
        setTheoryUnitNames([]);
        setCompletedTheoryAgents(new Set());
        setActiveTheoryAgent(null);
        break;

      case "solution_generated": {
        const name = event.agent_name as string;
        setActiveTheoryAgent(name);
        setTheoryUnitNames((prev) => prev.includes(name) ? prev : [...prev, name]);
        setCompletedTheoryAgents((prev) => new Set(prev).add(name));
        break;
      }

      case "round_start":
        setAnalysisStep("monitor_aggregating");
        setDebateRound(event.round as number);
        setAggregatedCount(event.aggregated_count as number);
        if ((event.round as number) > 1) setRevisionApplied(true);
        break;

      case "round_complete":
        setAggregatedCount(event.aggregated_count as number);
        break;

      case "practicality_start":
        setAnalysisStep("pass_to_practicality");
        setConclusionsDrifting(true);
        setPracticalityScores(new Map());
        setVotingAgentName(null);
        setTimeout(() => {
          setConclusionsDrifting(false);
          setAnalysisStep("practicality_voting");
        }, 4500);
        break;

      case "feasibility_score": {
        const agentName = event.agent_name as string;
        const score = event.score as number;
        setVotingAgentName(agentName);
        setPracticalityScores((prev) => {
          const next = new Map(prev);
          next.set(agentName, score);
          return next;
        });
        break;
      }

      case "repair_phase_start":
        setAnalysisStep("repairing");
        setRepairCount(event.count as number);
        break;

      case "repair_start":
        setAnalysisStep("repairing");
        break;

      case "repair_iteration":
        setRepairCount((prev) => prev + 1);
        break;

      case "termination":
        // Will be followed by "complete"
        break;

      case "veto": {
        setShowVeto(true);
        setRunNumber((event.restart_number as number) + 1);
        setTimeout(() => {
          setShowVeto(false);
          setAnalysisStep("theory_analyzing");
          setTheoryUnitNames([]);
          setCompletedTheoryAgents(new Set());
          setActiveTheoryAgent(null);
          setAggregatedCount(0);
          setDebateRound(0);
          setRevisionApplied(false);
          setPracticalityScores(new Map());
          setVotingAgentName(null);
        }, 3500);
        break;
      }

      case "complete": {
        const output = event.output as Record<string, unknown>;
        const budgetUsage = (output.budget_usage as Record<string, number>) || {};
        const repairStats = (output.repair_stats as Record<string, number>) || {};
        const result: AnalysisResult = {
          id: output.id as string,
          recommendations: (output.recommendations as Recommendation[]) || [],
          vetoed_solutions: (output.vetoed_solutions as Recommendation[]) || [],
          audit_trail: (output.audit_trail as AnalysisResult["audit_trail"]) || [],
          debate_rounds: (output.debate_rounds as number) || 0,
          veto_restarts: (output.veto_restarts as number) || 0,
          theory_units_created: (output.theory_units_created as number) || 0,
          total_tokens: (output.total_tokens as number) || 0,
          duration_ms: (output.duration_ms as number) || 0,
          termination_reason: (output.termination_reason as string) || "",
          budget_usage: {
            llm_calls: budgetUsage.llm_calls || 0,
            input_tokens: budgetUsage.input_tokens || 0,
            output_tokens: budgetUsage.output_tokens || 0,
            total_tokens: budgetUsage.total_tokens || 0,
            wallclock_ms: budgetUsage.wallclock_ms || 0,
          },
          mode_used: (output.mode_used as string) || "simple",
          repair_stats: {
            recommendations_repaired: repairStats.recommendations_repaired || 0,
            recommendations_recovered: repairStats.recommendations_recovered || 0,
            recommendations_failed_after_repairs: repairStats.recommendations_failed_after_repairs || 0,
            total_repair_iterations: repairStats.total_repair_iterations || 0,
          },
        };
        setAnalysisResult(result);
        setAnalysisStep("done");
        setTimeout(() => setShowOutputModal(true), 1000);
        break;
      }

      case "error":
        setAnalysisError(event.message as string);
        setAnalysisStep("done");
        break;
    }
  }

  function handleCancelAnalysis() {
    abortRef.current?.abort();
    setPhase("main");
  }

  // ---------------------------------------------------------------------------
  // Output helpers
  // ---------------------------------------------------------------------------

  function scoreClass(score: number): string {
    if (score >= 80) return "high";
    if (score >= 50) return "medium";
    return "low";
  }

  function statusLabel(status: string): string {
    if (status === "approved") return "APPROVED";
    if (status === "failed_after_repairs") return "FAILED AFTER REPAIRS";
    if (status === "vetoed") return "VETOED";
    return status.toUpperCase();
  }

  function terminationLabel(reason: string): string {
    const labels: Record<string, string> = {
      simple_completed: "Completed (simple mode)",
      sufficiency_reached: "Sufficiency target reached",
      max_rounds_reached: "Maximum debate rounds reached",
      stagnation_early_stop: "Stopped early (stagnation detected)",
      budget_exhausted: "Budget exhausted",
      completed_with_repairs: "Completed with repairs",
      global_restart_exhausted: "Global restart limit reached",
      validation_error: "Validation error",
    };
    return labels[reason] || reason;
  }

  function toggleRec(id: string) {
    setExpandedRecs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function downloadResults() {
    if (!analysisResult) return;
    const r = analysisResult;
    let text = "HIVEMIND STRATEGIC ANALYSIS REPORT\n";
    text += "=".repeat(40) + "\n\n";
    text += `Mode: ${r.mode_used} | Termination: ${terminationLabel(r.termination_reason)}\n`;
    text += `Debate rounds: ${r.debate_rounds} | Restarts: ${r.veto_restarts} | Units: ${r.theory_units_created}\n`;
    text += `Tokens: ${r.total_tokens} | LLM calls: ${r.budget_usage.llm_calls} | Duration: ${(r.duration_ms / 1000).toFixed(1)}s\n`;
    if (r.repair_stats.recommendations_repaired > 0) {
      text += `Repairs: ${r.repair_stats.recommendations_recovered} recovered, ${r.repair_stats.recommendations_failed_after_repairs} failed\n`;
    }
    text += "\n";

    text += "APPROVED RECOMMENDATIONS\n" + "-".repeat(30) + "\n\n";
    for (const rec of r.recommendations.filter(r => r.status === "approved")) {
      text += `[${Math.round(rec.average_feasibility)}/100] ${rec.title}\n`;
      text += `${rec.content}\n\n`;
      text += `Reasoning: ${rec.reasoning}\n\n`;
      for (const fs of rec.feasibility_scores) {
        text += `  - ${fs.agent_name}: ${fs.score}/100\n`;
        if (fs.risks.length) text += `    Risks: ${fs.risks.join("; ")}\n`;
        if (fs.mitigations.length) text += `    Mitigations: ${fs.mitigations.join("; ")}\n`;
      }
      text += "\n";
    }

    const failedRecs = r.recommendations.filter(r => r.status === "failed_after_repairs");
    if (failedRecs.length) {
      text += "FAILED AFTER REPAIRS\n" + "-".repeat(30) + "\n\n";
      for (const rec of failedRecs) {
        text += `[${Math.round(rec.average_feasibility)}/100] ${rec.title}\n`;
        text += `${rec.content}\n\n`;
      }
    }

    if (r.vetoed_solutions.length) {
      text += "VETOED SOLUTIONS\n" + "-".repeat(30) + "\n\n";
      for (const rec of r.vetoed_solutions) {
        text += `[${Math.round(rec.average_feasibility)}/100] ${rec.title}\n`;
        text += `${rec.content}\n\n`;
      }
    }

    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `hivemind-analysis-${r.id?.slice(0, 8) || "report"}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---------------------------------------------------------------------------
  // Explanation bar text
  // ---------------------------------------------------------------------------

  function getExplanation(): string {
    if (phase === "login") return "Enter your username to connect to the Hivemind server.";
    if (phase === "login_fade_out") return "Connecting to Hivemind...";
    if (phase === "main") {
      return `${analysisMode === "simple" ? "Simple" : "Full"} mode, ${effortLevel} effort. Set your problem and click Submit.`;
    }
    if (phase === "output") return analysisResult
      ? `Analysis complete. ${analysisResult.recommendations.filter(r => r.status === "approved").length} approved, ${analysisResult.vetoed_solutions.length} vetoed. ${terminationLabel(analysisResult.termination_reason)}.`
      : "";
    // analysis phase
    switch (analysisStep) {
      case "initializing":
        return "Initializing analysis stream...";
      case "theory_analyzing":
        return runNumber > 1
          ? `Theory network restarting (run ${runNumber}). Units generating revised solutions...`
          : "Theory network units are generating initial solutions using RAG-retrieved knowledge...";
      case "monitor_aggregating":
        return `Monitor is aggregating similar solutions. Round ${debateRound}, ${aggregatedCount} distinct conclusions.`;
      case "pass_to_practicality":
        return "Passing aggregated solutions to the practicality network for feasibility evaluation.";
      case "practicality_voting":
        return "Practicality agents are evaluating each solution's real-world feasibility (1-100).";
      case "repairing":
        return "Repairing low-feasibility recommendations to improve their scores...";
      case "veto":
        return "No recommendations passed threshold. Restarting analysis.";
      case "done":
        return analysisError
          ? `Analysis error: ${analysisError}`
          : analysisResult
          ? `${terminationLabel(analysisResult.termination_reason)}. ${analysisResult.recommendations.filter(r => r.status === "approved").length} approved.`
          : "Processing...";
    }
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const canSubmit =
    problemText.trim().length > 0 &&
    connectionStatus === "connected" &&
    (densityMode || selectedTheoryIds.size > 0 || decisionType);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      {/* --- LOGIN --- */}
      {phase === "login" && (
        <LoginScreen
          username={username}
          onUsernameChange={setUsername}
          password={password}
          onPasswordChange={setPassword}
          onSubmit={handleLogin}
          error={loginError}
          isLoading={loginLoading}
          connectionStatus={connectionStatus}
          onServerUrlChange={() => {
            if (healthRef.current) clearTimeout(healthRef.current);
            retryCountRef.current = 0;
            setConnectionStatus("connecting");
            runHealthCheck();
          }}
        />
      )}

      {/* --- LOGIN FADE --- */}
      {phase === "login_fade_out" && (
        <LoginFadeOut username={username} onDone={() => setPhase("main")} />
      )}

      {/* --- MAIN INPUT --- */}
      {phase === "main" && (
        <div className={`app-main main-fade-in ${showDataPanel ? "data-open" : ""}`}>
          <div className="main-content">
            <div className="main-header">
              <span className="main-brand">HIVEMIND</span>
              <span className="main-badge">CLIENT</span>
              <div className="header-connection">
                <span className={`connection-dot ${connectionStatus}`} />
                <span>{connectionStatus === "connected" ? "Online" : "Offline"}</span>
              </div>
              <button
                className="btn btn-secondary header-logout-btn"
                onClick={() => {
                  // Cancel any active analysis stream
                  abortRef.current?.abort();
                  abortRef.current = null;
                  // Stop health check polling
                  if (healthRef.current) clearTimeout(healthRef.current);
                  retryCountRef.current = 0;
                  setConnectionStatus("connecting");
                  // Clear auth
                  logout();
                  // Reset all state
                  setPhase("login");
                  setUsername("");
                  setPassword("");
                  setLoginError("");
                  setAgents([]);
                  setProblemText("");
                  setContextText("");
                  setClientId(null);
                  setClientDataEntries([]);
                  setScrapedSources([]);
                  setNewSourceUrl("");
                  setShowDataPanel(false);
                  setShowAdvanced(false);
                  setAnalysisResult(null);
                  setAnalysisError(null);
                  setAnalysisStep("initializing");
                  runHealthCheck();
                }}
              >
                Logout
              </button>
            </div>

            <div className="input-section">
              {/* Problem */}
              <div className="input-block">
                <label className="input-label">Problem description</label>
                <textarea
                  className="problem-input"
                  rows={5}
                  placeholder="Describe the strategic question you want Hivemind to analyze..."
                  value={problemText}
                  onChange={(e) => setProblemText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && canSubmit) {
                      e.preventDefault();
                      handleStartAnalysis();
                    }
                  }}
                />
              </div>

              {/* Mode selector */}
              <div className="input-block">
                <label className="input-label">Analysis mode</label>
                <div className="mode-selector">
                  <button
                    className={`mode-btn ${analysisMode === "simple" ? "active" : ""}`}
                    onClick={() => setAnalysisMode("simple")}
                  >
                    Simple
                  </button>
                  <button
                    className={`mode-btn ${analysisMode === "full" ? "active" : ""}`}
                    onClick={() => setAnalysisMode("full")}
                  >
                    Full
                  </button>
                </div>
                <div className="mode-description">
                  {analysisMode === "simple"
                    ? "Fast baseline: no debate rounds, quick feasibility check, lower cost."
                    : "Deep synthesis: multi-round critique, per-recommendation repair, higher quality."}
                </div>
              </div>

              {/* Effort selector */}
              <div className="input-block">
                <label className="input-label">Effort level</label>
                <div className="mode-selector effort-selector">
                  {(["low", "medium", "high"] as const).map((level) => (
                    <button
                      key={level}
                      className={`mode-btn ${effortLevel === level ? "active" : ""}`}
                      onClick={() => setEffortLevel(level)}
                    >
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </button>
                  ))}
                </div>
                <div className="mode-description">
                  {effortLevel === "low" && "Minimal cost: 2 rounds max, 30 LLM calls cap."}
                  {effortLevel === "medium" && "Balanced: 4 rounds max, 80 LLM calls cap."}
                  {effortLevel === "high" && "Maximum quality: 6 rounds max, 160 LLM calls cap."}
                </div>
              </div>

              {/* Primary sliders */}
              <SliderWithInput
                label="Sufficiency value"
                value={sufficiency}
                min={1}
                max={10}
                step={1}
                minLabel="Fewer conclusions"
                maxLabel="More conclusions"
                onChange={setSufficiency}
              />

              <SliderWithInput
                label="Feasibility threshold"
                value={feasibility}
                min={1}
                max={100}
                step={1}
                minLabel="Lenient"
                maxLabel="Strict"
                onChange={setFeasibility}
              />

              {/* Advanced toggle */}
              <button
                className="advanced-toggle"
                onClick={() => setShowAdvanced(!showAdvanced)}
              >
                {showAdvanced ? "Hide advanced" : "Advanced parameters"}
              </button>

              <div className={`advanced-params ${showAdvanced ? "open" : ""}`}>
                <div className="advanced-inner">
                  {/* Experimental badge */}
                  <div className="experimental-badge">EXPERIMENTAL</div>

                  {/* Density mode toggle */}
                  <div className="toggle-row">
                    <button
                      className={`toggle-switch ${densityMode ? "active" : ""}`}
                      onClick={() => setDensityMode(!densityMode)}
                    />
                    <span className="toggle-label">Dynamic density mode</span>
                  </div>

                  {densityMode && (
                    <SliderWithInput
                      label="Theory network density"
                      value={density}
                      min={densityMin}
                      max={densityMax}
                      step={500}
                      minLabel={`${densityMin.toLocaleString()} tokens`}
                      maxLabel={`${densityMax.toLocaleString()} tokens`}
                      onChange={setDensity}
                    />
                  )}

                  <SliderWithInput
                    label="Similarity threshold"
                    value={similarityThreshold}
                    min={0}
                    max={1}
                    step={0.05}
                    minLabel="Low similarity"
                    maxLabel="High similarity"
                    onChange={setSimilarityThreshold}
                  />

                  <SliderWithInput
                    label="Revision strength"
                    value={revisionStrength}
                    min={0}
                    max={1}
                    step={0.05}
                    minLabel="Preserve original"
                    maxLabel="Heavy revision"
                    onChange={setRevisionStrength}
                  />

                  <SliderWithInput
                    label="Practicality criticality"
                    value={practicalityCriticality}
                    min={0}
                    max={1}
                    step={0.05}
                    minLabel="Lenient"
                    maxLabel="Harsh"
                    onChange={setPracticalityCriticality}
                  />

                  {/* Dropdowns */}
                  <div className="input-block">
                    <label className="input-label">Use-case profile</label>
                    <select
                      className="form-select"
                      value={useCaseProfile}
                      onChange={(e) => setUseCaseProfile(e.target.value)}
                    >
                      <option value="">None (manual selection)</option>
                      <option value="small_business">Small Business</option>
                      <option value="individual_career">Individual / Career</option>
                      <option value="enterprise">Enterprise</option>
                    </select>
                  </div>

                  <div className="input-block">
                    <label className="input-label">Decision type</label>
                    <select
                      className="form-select"
                      value={decisionType}
                      onChange={(e) => setDecisionType(e.target.value)}
                    >
                      <option value="">None (manual selection)</option>
                      <option value="market_entry">Market Entry</option>
                      <option value="m_and_a">M&A</option>
                      <option value="pricing">Pricing</option>
                      <option value="business_model_change">Business Model Change</option>
                    </select>
                  </div>

                  {/* Agent selection */}
                  {!densityMode && theoryAgents.length > 0 && (
                    <div className="input-block">
                      <label className="input-label">Theory agents</label>
                      <div className="agent-checkbox-list">
                        {theoryAgents.map((a) => (
                          <label key={a.id} className="agent-checkbox">
                            <input
                              type="checkbox"
                              checked={selectedTheoryIds.has(a.id)}
                              onChange={() => {
                                setSelectedTheoryIds((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(a.id)) next.delete(a.id);
                                  else next.add(a.id);
                                  return next;
                                });
                              }}
                            />
                            <span>{a.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {practicalityAgents.length > 0 && (
                    <div className="input-block">
                      <label className="input-label">Practicality agents</label>
                      <div className="agent-checkbox-list">
                        {practicalityAgents.map((a) => (
                          <label key={a.id} className="agent-checkbox">
                            <input
                              type="checkbox"
                              checked={selectedPracticalityIds.has(a.id)}
                              onChange={() => {
                                setSelectedPracticalityIds((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(a.id)) next.delete(a.id);
                                  else next.add(a.id);
                                  return next;
                                });
                              }}
                            />
                            <span>{a.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Action buttons */}
              <div className="actions">
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowDataPanel(!showDataPanel)}
                >
                  {showDataPanel ? "Close data" : "Access data"}
                </button>
                <button
                  className="btn btn-primary"
                  disabled={!canSubmit}
                  onClick={handleStartAnalysis}
                >
                  Submit
                </button>
              </div>
            </div>
          </div>

          {/* Data panel */}
          {showDataPanel && (
            <div className="data-panel">
              <div className="data-panel-header">
                <span className="data-panel-title">Client Context</span>
                <button
                  className="data-panel-close"
                  onClick={() => setShowDataPanel(false)}
                  aria-label="Close"
                >
                  &times;
                </button>
              </div>
              <div className="data-panel-body">
                <span className="context-hint">
                  Paste any supporting data, financial reports, market research, or
                  other context the agents should consider.
                </span>
                <textarea
                  className="context-textarea"
                  placeholder="Paste context here..."
                  value={contextText}
                  onChange={(e) => setContextText(e.target.value)}
                />

                {/* My Data — persistent entries */}
                <div className="my-data-section">
                  <div className="my-data-header">
                    <span className="my-data-title">My Saved Data</span>
                    <span className="my-data-count">{clientDataEntries.length} entries</span>
                  </div>

                  {clientDataEntries.length > 0 && (
                    <div className="my-data-list">
                      {clientDataEntries.map((entry) => (
                        <div key={entry.id} className="data-entry-row">
                          <div className="data-entry-info">
                            <span className="data-entry-label">
                              {entry.metadata?.source === "file_upload" ? "[file] " : ""}
                              {entry.label}
                            </span>
                            <span className="data-entry-preview">
                              {entry.content.slice(0, 100)}{entry.content.length > 100 ? "..." : ""}
                            </span>
                          </div>
                          <button
                            className="data-entry-delete"
                            onClick={async () => {
                              if (!clientId) return;
                              try {
                                await deleteClientData(clientId, entry.id);
                                setClientDataEntries((prev) => prev.filter((e) => e.id !== entry.id));
                              } catch { /* ignore */ }
                            }}
                            aria-label="Delete"
                          >
                            &times;
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="data-add-form">
                    <input
                      type="text"
                      className="data-add-label"
                      placeholder="Label (e.g. Q4 Report)"
                      value={newEntryLabel}
                      onChange={(e) => setNewEntryLabel(e.target.value)}
                    />
                    <textarea
                      className="data-add-content"
                      placeholder="Paste content..."
                      value={newEntryContent}
                      onChange={(e) => setNewEntryContent(e.target.value)}
                      rows={3}
                    />
                    <button
                      className="btn btn-secondary data-add-save"
                      disabled={!newEntryLabel.trim() || !newEntryContent.trim() || !clientId || savingEntry}
                      onClick={async () => {
                        if (!clientId || !newEntryLabel.trim() || !newEntryContent.trim()) return;
                        setSavingEntry(true);
                        try {
                          const created = await createClientData(clientId, newEntryLabel.trim(), newEntryContent.trim());
                          setClientDataEntries((prev) => [...prev, created]);
                          setNewEntryLabel("");
                          setNewEntryContent("");
                        } catch { /* ignore */ }
                        setSavingEntry(false);
                      }}
                    >
                      {savingEntry ? "Saving..." : "Save entry"}
                    </button>

                    <div className="data-upload-divider">— or upload a file —</div>
                    <div className="data-upload-row">
                      <input
                        type="file"
                        accept=".pdf,.docx,.doc,.txt,.html,.csv"
                        className="data-upload-input"
                        onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      />
                      <button
                        className="btn btn-secondary data-upload-btn"
                        disabled={!uploadFile || !clientId || uploading}
                        onClick={async () => {
                          if (!uploadFile || !clientId) return;
                          setUploading(true);
                          try {
                            const created = await uploadClientData(clientId, uploadFile);
                            setClientDataEntries((prev) => [...prev, created]);
                            setUploadFile(null);
                            const input = document.querySelector('.data-upload-input') as HTMLInputElement;
                            if (input) input.value = '';
                          } catch { /* ignore */ }
                          setUploading(false);
                        }}
                      >
                        {uploading ? "Uploading..." : "Upload"}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Web Sources — scraped URLs and search queries */}
                <div className="web-sources-section">
                  <div className="my-data-header">
                    <span className="my-data-title">Web Sources</span>
                    <span className="my-data-count">{scrapedSources.length} sources</span>
                  </div>
                  <div className="source-mode-toggle">
                    <button
                      className={`source-mode-btn ${sourceMode === "url" ? "active" : ""}`}
                      onClick={() => setSourceMode("url")}
                    >
                      URL
                    </button>
                    <button
                      className={`source-mode-btn ${sourceMode === "search_query" ? "active" : ""}`}
                      onClick={() => setSourceMode("search_query")}
                    >
                      Search
                    </button>
                  </div>

                  {scrapedSources.length > 0 && (
                    <div className="my-data-list">
                      {scrapedSources.map((src) => (
                        <div key={src.id} className="source-row">
                          <div className="data-entry-info">
                            <span className="source-url" title={src.url_or_query}>
                              {src.url_or_query.length > 40
                                ? src.url_or_query.slice(0, 40) + "..."
                                : src.url_or_query}
                            </span>
                            {src.source_type === "search_query" && (
                              <span className="source-type-badge">search</span>
                            )}
                            <span className={`source-status-badge status-${src.status}`}>
                              {src.status}
                            </span>
                          </div>
                          <div className="source-actions">
                            {src.status !== "completed" && (
                              <button
                                className="btn btn-secondary source-action-btn"
                                onClick={async () => {
                                  try {
                                    const result = await triggerScrape(src.id);
                                    setScrapedSources((prev) =>
                                      prev.map((s) =>
                                        s.id === src.id ? { ...s, status: result.status } : s
                                      )
                                    );
                                  } catch { /* ignore */ }
                                }}
                              >
                                Scrape
                              </button>
                            )}
                            <button
                              className="data-entry-delete"
                              onClick={async () => {
                                try {
                                  await deleteScrapedSource(src.id);
                                  setScrapedSources((prev) => prev.filter((s) => s.id !== src.id));
                                } catch { /* ignore */ }
                              }}
                              aria-label="Delete"
                            >
                              &times;
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="data-add-form">
                    <input
                      type="text"
                      className="data-add-label"
                      placeholder={sourceMode === "url" ? "https://example.com/article" : "Search query..."}
                      value={newSourceUrl}
                      onChange={(e) => setNewSourceUrl(e.target.value)}
                    />
                    <button
                      className="btn btn-secondary data-add-save"
                      disabled={!newSourceUrl.trim()}
                      onClick={async () => {
                        const url = newSourceUrl.trim();
                        if (!url) return;
                        try {
                          const created = await createScrapedSource(url, sourceMode);
                          setScrapedSources((prev) => [created, ...prev]);
                          setNewSourceUrl("");
                          // Auto-trigger scrape
                          try {
                            const result = await triggerScrape(created.id);
                            setScrapedSources((prev) =>
                              prev.map((s) =>
                                s.id === created.id ? { ...s, status: result.status } : s
                              )
                            );
                          } catch { /* ignore */ }
                        } catch { /* ignore */ }
                      }}
                    >
                      {sourceMode === "url" ? "Add URL" : "Search"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* --- ANALYSIS VIEW --- */}
      {phase === "analysis" && (
        <div className="app-analysis">
          <div className="main-header analysis-header">
            <span className="main-brand">HIVEMIND</span>
            <span className="main-badge">ANALYSIS</span>
            <span className="main-badge" style={{ borderColor: analysisMode === "full" ? "#00bfff" : "#7fba00" }}>
              {analysisMode.toUpperCase()}
            </span>
            {runNumber > 1 && (
              <span className="main-badge" style={{ borderColor: "#ff2a2a", color: "#ff2a2a" }}>
                RUN {runNumber}
              </span>
            )}
            <button className="btn btn-cancel" onClick={handleCancelAnalysis}>
              Cancel
            </button>
          </div>

          <div className="analysis-grid">
            {/* Theory panel */}
            <div
              className={`panel theory-panel ${
                analysisStep === "theory_analyzing" ? "active" : ""
              }`}
            >
              <h3 className="panel-title">
                Theory Network
                {theoryUnitNames.length > 0 && (
                  <span className="monitor-count">
                    {completedTheoryAgents.size}/{theoryUnitNames.length} units
                  </span>
                )}
              </h3>
              <ul className="unit-list">
                {theoryUnitNames.map((name) => (
                  <li
                    key={name}
                    className={`unit-item ${
                      activeTheoryAgent === name && analysisStep === "theory_analyzing"
                        ? "active"
                        : completedTheoryAgents.has(name)
                        ? "completed"
                        : ""
                    }`}
                  >
                    {name}
                  </li>
                ))}
                {analysisStep === "theory_analyzing" && theoryUnitNames.length === 0 && (
                  <li className="unit-item active">Generating solutions...</li>
                )}
              </ul>
            </div>

            {/* Monitor panel */}
            <div className="panel monitor-panel">
              <h3 className="panel-title">
                Monitor
                {aggregatedCount > 0 && (
                  <span className="monitor-count">Conclusions: {aggregatedCount}</span>
                )}
              </h3>
              <div className="monitor-box">
                {analysisStep === "initializing" && (
                  <div className="monitor-status">Waiting for stream...</div>
                )}
                {analysisStep === "theory_analyzing" && (
                  <div className="monitor-status">Waiting for theory units to complete...</div>
                )}
                {analysisStep === "monitor_aggregating" && (
                  <>
                    <div className="monitor-round">Round {debateRound}</div>
                    {revisionApplied && (
                      <div className="monitor-revision-label">Revision applied</div>
                    )}
                    <div className="monitor-status">
                      Aggregating {aggregatedCount} distinct conclusions...
                    </div>
                  </>
                )}
                {analysisStep === "repairing" && (
                  <div className="monitor-status repair-status">
                    Repairing low-feasibility recommendations...
                  </div>
                )}
                {(analysisStep === "pass_to_practicality" || analysisStep === "practicality_voting") && (
                  <div className="monitor-drifting">Passing to practicality network...</div>
                )}
                {analysisStep === "done" && analysisResult && (
                  <>
                    {analysisResult.recommendations.map((rec, i) => (
                      <div key={i} className="monitor-conclusion">
                        <span className={`rec-status-dot ${rec.status}`} />
                        {rec.title}
                      </div>
                    ))}
                  </>
                )}
                {analysisStep === "done" && analysisError && (
                  <div className="monitor-status" style={{ color: "#ff6b6b" }}>
                    Error: {analysisError}
                  </div>
                )}
              </div>
            </div>

            {/* Practicality panel */}
            <div className="panel">
              <h3 className="panel-title">Practicality Network</h3>
              <ul className="unit-list">
                {practicalityAgents.map((a) => (
                  <li
                    key={a.id}
                    className={`unit-item ${votingAgentName === a.name ? "voting" : ""}`}
                  >
                    <span>{a.name}</span>
                    {practicalityScores.has(a.name) && (
                      <span className="feasibility-score">
                        {practicalityScores.get(a.name)}/100
                      </span>
                    )}
                  </li>
                ))}
                {practicalityAgents.length === 0 && analysisStep === "practicality_voting" && (
                  <li className="unit-item">Evaluating...</li>
                )}
              </ul>
              {analysisStep === "practicality_voting" && (
                <div className="voting-label">Evaluating feasibility...</div>
              )}
            </div>
          </div>

          {/* Drift orbit animation */}
          {conclusionsDrifting && (
            <div className="drift-orbit" aria-hidden>
              {Array.from({ length: Math.min(aggregatedCount, 3) }, (_, i) => (
                <div key={i} className="drift-chip">
                  Solution {i + 1}
                </div>
              ))}
            </div>
          )}

          {/* Veto overlay */}
          {showVeto && (
            <div className="veto-overlay">
              <div className="veto-box">RESTART</div>
              <div className="veto-caption">
                No recommendations passed threshold — restarting analysis
              </div>
            </div>
          )}
        </div>
      )}

      {/* --- OUTPUT MODAL --- */}
      {(phase === "analysis" || phase === "output") && showOutputModal && analysisResult && (
        <div className="output-overlay" onClick={() => {
          setShowOutputModal(false);
          setPhase("main");
        }}>
          <div className="output-modal" onClick={(e) => e.stopPropagation()}>
            <div className="output-header">
              <h2>Analysis Complete</h2>
              <button
                className="output-close"
                onClick={() => {
                  setShowOutputModal(false);
                  setPhase("main");
                }}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <div className="output-body">
              {/* Termination reason */}
              <div className="termination-banner">
                {terminationLabel(analysisResult.termination_reason)}
              </div>

              {/* Stats bar */}
              <div className="stats-bar">
                <span className="stat-item">
                  <span className="stat-label">Mode</span>
                  <span className="stat-value">{analysisResult.mode_used}</span>
                </span>
                <span className="stat-item">
                  <span className="stat-label">Rounds</span>
                  <span className="stat-value">{analysisResult.debate_rounds}</span>
                </span>
                <span className="stat-item">
                  <span className="stat-label">LLM calls</span>
                  <span className="stat-value">{analysisResult.budget_usage.llm_calls}</span>
                </span>
                <span className="stat-item">
                  <span className="stat-label">Tokens</span>
                  <span className="stat-value">{analysisResult.total_tokens.toLocaleString()}</span>
                </span>
                <span className="stat-item">
                  <span className="stat-label">Duration</span>
                  <span className="stat-value">{(analysisResult.duration_ms / 1000).toFixed(1)}s</span>
                </span>
              </div>

              {/* Repair summary */}
              {analysisResult.repair_stats.recommendations_repaired > 0 && (
                <div className="repair-summary">
                  <span className="repair-summary-label">Repairs:</span>
                  <span className="repair-stat recovered">
                    {analysisResult.repair_stats.recommendations_recovered} recovered
                  </span>
                  {analysisResult.repair_stats.recommendations_failed_after_repairs > 0 && (
                    <span className="repair-stat failed">
                      {analysisResult.repair_stats.recommendations_failed_after_repairs} failed
                    </span>
                  )}
                  <span className="repair-stat iterations">
                    {analysisResult.repair_stats.total_repair_iterations} iterations
                  </span>
                </div>
              )}

              {/* Approved recommendations */}
              {analysisResult.recommendations.length > 0 && (
                <div>
                  <h3 className="rec-section-title">Recommendations</h3>
                  {analysisResult.recommendations.map((rec) => (
                    <div key={rec.id} className={`recommendation-card ${rec.status === "failed_after_repairs" ? "failed-card" : ""}`}>
                      <div className="rec-header" onClick={() => toggleRec(rec.id)}>
                        <span className={`rec-status-badge ${rec.status}`}>
                          {statusLabel(rec.status)}
                        </span>
                        <span className="rec-title">{rec.title}</span>
                        <span className={`rec-score ${scoreClass(rec.average_feasibility)}`}>
                          {Math.round(rec.average_feasibility)}/100
                        </span>
                        <span className="rec-expand">
                          {expandedRecs.has(rec.id) ? "\u25B2" : "\u25BC"}
                        </span>
                      </div>
                      {expandedRecs.has(rec.id) && (
                        <div className="rec-body">
                          <div className="rec-body-section">
                            <span className="rec-body-label">Content</span>
                            <div className="rec-body-text">{rec.content}</div>
                          </div>
                          <div className="rec-body-section">
                            <span className="rec-body-label">Reasoning</span>
                            <div className="rec-body-text">{rec.reasoning}</div>
                          </div>
                          {rec.repair_history && rec.repair_history.length > 0 && (
                            <div className="rec-body-section">
                              <span className="rec-body-label">Repair History</span>
                              <div className="repair-history-list">
                                {rec.repair_history.map((rh, idx) => (
                                  <div key={idx} className="repair-history-item">
                                    <span>Iteration {rh.iteration}: {Math.round(rh.score_before)} → {Math.round(rh.score_after)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {rec.feasibility_scores.length > 0 && (
                            <div className="rec-body-section">
                              <span className="rec-body-label">Feasibility Scores</span>
                              <div className="rec-feasibility-list">
                                {rec.feasibility_scores.map((fs, idx) => (
                                  <div key={idx} className="rec-feasibility-item">
                                    <div className="rec-feasibility-agent">
                                      <span>{fs.agent_name}</span>
                                      <span className="feasibility-score">{fs.score}/100</span>
                                    </div>
                                    {fs.risks.length > 0 && (
                                      <div className="rec-feasibility-detail">
                                        Risks: {fs.risks.join("; ")}
                                      </div>
                                    )}
                                    {fs.challenges.length > 0 && (
                                      <div className="rec-feasibility-detail">
                                        Challenges: {fs.challenges.join("; ")}
                                      </div>
                                    )}
                                    {fs.mitigations.length > 0 && (
                                      <div className="rec-feasibility-detail">
                                        Mitigations: {fs.mitigations.join("; ")}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Vetoed solutions */}
              {analysisResult.vetoed_solutions.length > 0 && (
                <div className="vetoed-section">
                  <h3 className="rec-section-title">Vetoed Solutions</h3>
                  {analysisResult.vetoed_solutions.map((rec) => (
                    <div key={rec.id} className="recommendation-card">
                      <div className="rec-header" onClick={() => toggleRec(rec.id)}>
                        <span className="rec-status-badge vetoed">VETOED</span>
                        <span className="rec-title">{rec.title}</span>
                        <span className={`rec-score ${scoreClass(rec.average_feasibility)}`}>
                          {Math.round(rec.average_feasibility)}/100
                        </span>
                        <span className="rec-expand">
                          {expandedRecs.has(rec.id) ? "\u25B2" : "\u25BC"}
                        </span>
                      </div>
                      {expandedRecs.has(rec.id) && (
                        <div className="rec-body">
                          <div className="rec-body-section">
                            <span className="rec-body-label">Content</span>
                            <div className="rec-body-text">{rec.content}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Audit trail */}
              {analysisResult.audit_trail.length > 0 && (
                <div>
                  <button className="audit-toggle" onClick={() => setShowAudit(!showAudit)}>
                    {showAudit ? "Hide audit trail" : `Show audit trail (${analysisResult.audit_trail.length} events)`}
                  </button>
                  {showAudit && (
                    <div className="audit-list">
                      {analysisResult.audit_trail.map((evt, idx) => (
                        <div key={idx} className="audit-event">
                          <span className="audit-event-type">{evt.event_type}</span>
                          {evt.agent_id && <span> | {evt.agent_id.slice(0, 8)}</span>}
                          {evt.input_tokens != null && (
                            <span> | {evt.input_tokens}+{evt.output_tokens} tokens</span>
                          )}
                          {evt.latency_ms != null && <span> | {evt.latency_ms}ms</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="output-footer">
              <button className="btn-download" onClick={downloadResults}>
                Download as TXT
              </button>
              <button
                className="btn-download"
                onClick={() => {
                  setShowOutputModal(false);
                  setPhase("main");
                }}
              >
                New Analysis
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --- ERROR VIEW --- */}
      {phase === "analysis" && analysisStep === "done" && analysisError && !showOutputModal && (
        <div className="error-view">
          <div className="error-message">{analysisError}</div>
          <button className="btn btn-primary" onClick={() => setPhase("main")}>
            Return to Input
          </button>
        </div>
      )}

      {/* --- EXPLANATION BAR --- */}
      <div className="explanation-bar" role="status">
        <span className="explanation-text">{getExplanation()}</span>
        <img src="/hivemind-icon.png" alt="" className="explanation-icon" draggable={false} />
      </div>
    </>
  );
}
