/**
 * API client for Hivemind Cloud Services.
 * Used by the Client app to run analyses and sync with the server.
 */

/**
 * API URL - checks localStorage first (set via Configure server), then env var,
 * then falls back to AWS deployment.
 */
const DEFAULT_API_URL = "http://13.63.209.56:8000";

function getEffectiveApiUrl(): string {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("hivemind_api_url");
    if (stored) return stored.replace(/\/+$/, "");
  }
  return import.meta.env.VITE_API_URL || DEFAULT_API_URL;
}

let API_URL = getEffectiveApiUrl();

/** Change the server URL at runtime (persisted in localStorage). */
export function setServerUrl(url: string): void {
  const clean = url.replace(/\/+$/, "");
  localStorage.setItem("hivemind_api_url", clean);
  API_URL = clean;
}

/** Reset to the build-time default URL. */
export function clearServerUrl(): void {
  localStorage.removeItem("hivemind_api_url");
  API_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;
}

export function isCustomServerUrl(): boolean {
  return !!localStorage.getItem("hivemind_api_url");
}

export function getDefaultApiUrl(): string {
  return import.meta.env.VITE_API_URL || DEFAULT_API_URL;
}

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface Agent {
  id: string;
  name: string;
  network_type: "theory" | "practicality";
  description?: string;
  framework?: string;
}

export interface AnalysisRequest {
  problem_statement: string;
  analysis_mode?: "simple" | "full";
  effort_level?: "low" | "medium" | "high";
  context_documents?: string[];
  context_document_texts?: string[];
  sufficiency_value?: number;
  feasibility_threshold?: number;
  max_total_llm_calls?: number | null;
  max_total_tokens?: number | null;
  max_wallclock_ms?: number | null;
  max_repair_iterations?: number;
  theory_network_density?: number | null;
  enabled_theory_agent_ids?: string[];
  enabled_practicality_agent_ids?: string[];
  max_veto_restarts?: number;
  similarity_threshold?: number;
  revision_strength?: number;
  practicality_criticality?: number;
  use_case_profile?: string | null;
  decision_type?: string | null;
  // Legacy fields for backward compatibility
  theory_agent_ids?: string[];
  practicality_agent_ids?: string[];
  debate_rounds?: number;
}

export interface FeasibilityScore {
  agent_id: string;
  agent_name: string;
  score: number;
  risks: string[];
  challenges: string[];
  mitigations: string[];
  reasoning: string;
}

export interface RepairHistoryEntry {
  iteration: number;
  feedback_summary: string;
  score_before: number;
  score_after: number;
}

export interface Recommendation {
  id: string;
  title: string;
  content: string;
  reasoning: string;
  contributing_agents: string[];
  retrieved_chunk_ids: string[];
  feasibility_scores: FeasibilityScore[];
  average_feasibility: number;
  status: "approved" | "vetoed" | "failed_after_repairs";
  repair_history: RepairHistoryEntry[];
}

export interface AuditEvent {
  event_type: string;
  timestamp?: string;
  agent_id?: string;
  details?: Record<string, unknown>;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
}

export interface BudgetUsage {
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  wallclock_ms: number;
}

export interface RepairStats {
  recommendations_repaired: number;
  recommendations_recovered: number;
  recommendations_failed_after_repairs: number;
  total_repair_iterations: number;
}

export interface AnalysisResult {
  id: string;
  recommendations: Recommendation[];
  vetoed_solutions: Recommendation[];
  audit_trail: AuditEvent[];
  debate_rounds: number;
  veto_restarts: number;
  theory_units_created: number;
  total_tokens: number;
  duration_ms: number;
  termination_reason: string;
  budget_usage: BudgetUsage;
  mode_used: string;
  repair_stats: RepairStats;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface EnterMenuCredentials {
  username: string;
  password: string;
}

// -----------------------------------------------------------------------------
// Token Storage
// -----------------------------------------------------------------------------

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) {
    localStorage.setItem("hivemind_token", token);
    _scheduleTokenRefresh();
  } else {
    localStorage.removeItem("hivemind_token");
    if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null; }
  }
}

export function getAuthToken(): string | null {
  if (!authToken) {
    authToken = localStorage.getItem("hivemind_token");
    if (authToken) _scheduleTokenRefresh();
  }
  return authToken;
}

// -----------------------------------------------------------------------------
// Proactive Token Refresh
// -----------------------------------------------------------------------------

let _refreshTimer: ReturnType<typeof setTimeout> | null = null;

function _decodeTokenExp(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

function _scheduleTokenRefresh(): void {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  const token = getAuthToken();
  if (!token) return;
  const exp = _decodeTokenExp(token);
  if (!exp) return;
  // Refresh 5 minutes before expiry (or immediately if < 5 min remain)
  const nowSec = Math.floor(Date.now() / 1000);
  const delayMs = Math.max((exp - nowSec - 300) * 1000, 0);
  _refreshTimer = setTimeout(async () => {
    try {
      const res = await request<{ access_token: string }>("/auth/refresh", {
        method: "POST",
      });
      setAuthToken(res.access_token);
      _scheduleTokenRefresh(); // schedule next refresh
    } catch {
      // Token refresh failed — user will need to re-login on next 401
    }
  }, delayMs);
}

// -----------------------------------------------------------------------------
// API Client
// -----------------------------------------------------------------------------

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${path}`;
  const token = getAuthToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    ...options,
    headers,
    mode: "cors",
    credentials: "omit",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }

  return res.json();
}

// -----------------------------------------------------------------------------
// Authentication
// -----------------------------------------------------------------------------

export async function enterSystem(
  credentials: EnterMenuCredentials
): Promise<AuthResponse> {
  const response = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  setAuthToken(response.access_token);
  return response;
}

export function logout() {
  setAuthToken(null);
}

// -----------------------------------------------------------------------------
// Agents
// -----------------------------------------------------------------------------

export async function listPublishedAgents(): Promise<Agent[]> {
  return request<Agent[]>("/agents?status=published");
}

export async function syncAgents(): Promise<{ agents: Agent[]; synced_at: string }> {
  return request("/sync/agents");
}

// -----------------------------------------------------------------------------
// Analysis
// -----------------------------------------------------------------------------

/**
 * Start a new strategic analysis.
 */
export async function startAnalysis(req: AnalysisRequest): Promise<AnalysisResult> {
  const payload = {
    problem_statement: req.problem_statement,
    analysis_mode: req.analysis_mode ?? "simple",
    effort_level: req.effort_level ?? "medium",
    context_documents: req.context_documents ?? [],
    context_document_texts: req.context_document_texts ?? [],
    sufficiency_value: req.sufficiency_value ?? 1,
    feasibility_threshold: req.feasibility_threshold ?? 80,
    ...(req.max_total_llm_calls != null && { max_total_llm_calls: req.max_total_llm_calls }),
    ...(req.max_total_tokens != null && { max_total_tokens: req.max_total_tokens }),
    ...(req.max_wallclock_ms != null && { max_wallclock_ms: req.max_wallclock_ms }),
    max_repair_iterations: req.max_repair_iterations ?? 2,
    theory_network_density: req.theory_network_density ?? null,
    enabled_theory_agent_ids: req.enabled_theory_agent_ids ?? req.theory_agent_ids ?? [],
    enabled_practicality_agent_ids: req.enabled_practicality_agent_ids ?? req.practicality_agent_ids ?? [],
    max_veto_restarts: req.max_veto_restarts ?? 3,
    similarity_threshold: req.similarity_threshold ?? 0.65,
    revision_strength: req.revision_strength ?? 0.5,
    practicality_criticality: req.practicality_criticality ?? 0.5,
    ...(req.use_case_profile != null && { use_case_profile: req.use_case_profile }),
    ...(req.decision_type != null && { decision_type: req.decision_type }),
  };

  return request<AnalysisResult>("/analysis/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Get a previous analysis by ID.
 */
export async function getAnalysisStatus(analysisId: string): Promise<AnalysisResult> {
  return request<AnalysisResult>(`/analysis/${analysisId}`);
}

/**
 * Get the audit trail for an analysis.
 */
export async function getAnalysisAudit(analysisId: string): Promise<{ audit_trail: AuditEvent[] }> {
  return request(`/analysis/${analysisId}/audit`);
}

// -----------------------------------------------------------------------------
// Density Bounds
// -----------------------------------------------------------------------------

export interface DensityBounds {
  min_doc_tokens: number;
  sum_all_doc_tokens: number;
}

/**
 * Fetch density bounds from the server for the given knowledge base IDs.
 * Falls back to null if the endpoint fails or returns no data.
 */
export async function getDensityBounds(kbIds: string[]): Promise<DensityBounds | null> {
  if (!kbIds.length) return null;
  try {
    return await request<DensityBounds>(
      `/knowledge-bases/density-bounds?kb_ids=${kbIds.join(",")}`
    );
  } catch {
    return null;
  }
}

// -----------------------------------------------------------------------------
// SSE Streaming Analysis
// -----------------------------------------------------------------------------

export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

/**
 * Start a streaming analysis via Server-Sent Events.
 * Returns an AbortController to cancel the stream.
 */
export function startAnalysisStreaming(
  req: AnalysisRequest,
  onEvent: (event: StreamEvent) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController();

  const payload = {
    problem_statement: req.problem_statement,
    analysis_mode: req.analysis_mode ?? "simple",
    effort_level: req.effort_level ?? "medium",
    context_documents: req.context_documents ?? [],
    context_document_texts: req.context_document_texts ?? [],
    sufficiency_value: req.sufficiency_value ?? 1,
    feasibility_threshold: req.feasibility_threshold ?? 80,
    ...(req.max_total_llm_calls != null && { max_total_llm_calls: req.max_total_llm_calls }),
    ...(req.max_total_tokens != null && { max_total_tokens: req.max_total_tokens }),
    ...(req.max_wallclock_ms != null && { max_wallclock_ms: req.max_wallclock_ms }),
    max_repair_iterations: req.max_repair_iterations ?? 2,
    theory_network_density: req.theory_network_density ?? null,
    enabled_theory_agent_ids: req.enabled_theory_agent_ids ?? req.theory_agent_ids ?? [],
    enabled_practicality_agent_ids: req.enabled_practicality_agent_ids ?? req.practicality_agent_ids ?? [],
    max_veto_restarts: req.max_veto_restarts ?? 3,
    similarity_threshold: req.similarity_threshold ?? 0.65,
    revision_strength: req.revision_strength ?? 0.5,
    practicality_criticality: req.practicality_criticality ?? 0.5,
    ...(req.use_case_profile != null && { use_case_profile: req.use_case_profile }),
    ...(req.decision_type != null && { decision_type: req.decision_type }),
  };

  const token = getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  (async () => {
    try {
      const res = await fetch(`${API_URL}/analysis/run/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
        mode: "cors",
        credentials: "omit",
      });

      if (!res.ok) {
        const text = await res.text();
        onError(`API Error ${res.status}: ${text}`);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop()!;
        for (const part of parts) {
          const trimmed = part.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const json = JSON.parse(trimmed.slice(6));
              onEvent(json);
            } catch {
              // skip malformed events
            }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        onError((err as Error).message || "Stream connection failed");
      }
    }
  })();

  return controller;
}

// -----------------------------------------------------------------------------
// WebSocket for Real-Time Updates
// -----------------------------------------------------------------------------

export interface StreamCallbacks {
  onDebateStart?: (details: { query: string; theory_agents: number; practicality_agents: number }) => void;
  onSolutionGenerated?: (data: { unit_id: string; unit_name: string; solution: string }) => void;
  onCritique?: (data: { source: string; target: string; critique: string }) => void;
  onRevision?: (data: { unit_id: string; revised_solution: string }) => void;
  onAggregation?: (data: { aggregated_count: number }) => void;
  onFeasibilityScore?: (data: { recommendation_id: string; agent_name: string; score: number }) => void;
  onVeto?: (data: { reason: string; restart_number: number }) => void;
  onComplete?: (result: AnalysisResult) => void;
  onError?: (error: string) => void;
}

export function connectToAnalysisStream(
  analysisId: string,
  callbacks: StreamCallbacks
): WebSocket {
  const wsUrl = API_URL.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
  const token = getAuthToken();
  const wsUri = token
    ? `${wsUrl}/ws/analysis/${analysisId}?token=${encodeURIComponent(token)}`
    : `${wsUrl}/ws/analysis/${analysisId}`;
  const ws = new WebSocket(wsUri);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "debate_start":
          callbacks.onDebateStart?.(data.payload);
          break;
        case "solution_generated":
          callbacks.onSolutionGenerated?.(data.payload);
          break;
        case "critique":
          callbacks.onCritique?.(data.payload);
          break;
        case "revision":
          callbacks.onRevision?.(data.payload);
          break;
        case "aggregation":
          callbacks.onAggregation?.(data.payload);
          break;
        case "feasibility_score":
          callbacks.onFeasibilityScore?.(data.payload);
          break;
        case "veto":
          callbacks.onVeto?.(data.payload);
          break;
        case "complete":
          callbacks.onComplete?.(data.payload);
          break;
        case "error":
          callbacks.onError?.(data.message);
          break;
      }
    } catch (err) {
      callbacks.onError?.("Failed to parse WebSocket message");
    }
  };

  ws.onerror = () => {
    callbacks.onError?.("WebSocket connection error");
  };

  return ws;
}

// -----------------------------------------------------------------------------
// Identity
// -----------------------------------------------------------------------------

export interface UserIdentity {
  username: string;
  role: string;
  client_id: string;
}

export async function getMe(): Promise<UserIdentity> {
  return request<UserIdentity>("/auth/me");
}

// -----------------------------------------------------------------------------
// Client Data (persistent context entries)
// -----------------------------------------------------------------------------

export interface ClientDataEntry {
  id: string;
  client_id: string;
  label: string;
  content: string;
  metadata?: Record<string, unknown>;
}

export async function listClientData(clientId: string): Promise<ClientDataEntry[]> {
  return request<ClientDataEntry[]>(`/clients/${clientId}/data`);
}

export async function createClientData(
  clientId: string,
  label: string,
  content: string,
): Promise<ClientDataEntry> {
  return request<ClientDataEntry>(`/clients/${clientId}/data`, {
    method: "POST",
    body: JSON.stringify({ label, content }),
  });
}

export async function deleteClientData(clientId: string, dataId: string): Promise<void> {
  await request(`/clients/${clientId}/data/${dataId}`, { method: "DELETE" });
}

export async function uploadClientData(
  clientId: string,
  file: File,
  label?: string,
): Promise<ClientDataEntry> {
  const formData = new FormData();
  formData.append("file", file);
  if (label) formData.append("label", label);

  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(
    `${API_URL}/clients/${clientId}/data/upload`,
    { method: "POST", body: formData, headers, mode: "cors", credentials: "omit" }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${text}`);
  }
  return res.json();
}

// -----------------------------------------------------------------------------
// Scraped Sources (Web Sources)
// -----------------------------------------------------------------------------

export interface ScrapedSource {
  id: string;
  url_or_query: string;
  source_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

export async function listScrapedSources(): Promise<ScrapedSource[]> {
  return request<ScrapedSource[]>("/scraped-sources");
}

export async function createScrapedSource(
  urlOrQuery: string,
  sourceType: "url" | "search_query" = "url",
): Promise<ScrapedSource> {
  return request<ScrapedSource>("/scraped-sources", {
    method: "POST",
    body: JSON.stringify({ url_or_query: urlOrQuery, source_type: sourceType }),
  });
}

export async function triggerScrape(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/scraped-sources/${id}/scrape`, {
    method: "POST",
  });
}

export async function deleteScrapedSource(id: string): Promise<void> {
  await request(`/scraped-sources/${id}`, { method: "DELETE" });
}

// -----------------------------------------------------------------------------
// Health Check
// -----------------------------------------------------------------------------

export async function checkServerHealth(): Promise<{ status: string; version: string; connected: boolean }> {
  const urlsToTry = [API_URL];

  for (const url of urlsToTry) {
    try {
      const res = await fetch(`${url}/health`, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        return { ...data, connected: true };
      }
    } catch {
      continue;
    }
  }

  return { status: "disconnected", version: "unknown", connected: false };
}

/**
 * Get the current API URL (useful for debugging/display)
 */
export function getApiUrl(): string {
  return API_URL;
}
