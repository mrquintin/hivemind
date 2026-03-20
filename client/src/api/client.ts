/**
 * API client for Hivemind Cloud Services.
 * Used by the Client app to run analyses and sync with the server.
 */

/**
 * API URL - checks localStorage first (set via settings), then env var,
 * then falls back to production.
 */
function getEffectiveApiUrl(): string {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("hivemind_api_url");
    if (stored) return stored.replace(/\/+$/, "");
  }
  return (
    import.meta.env.VITE_API_URL || "https://www.thenashlabhivemind.com"
  );
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
  API_URL =
    import.meta.env.VITE_API_URL || "https://www.thenashlabhivemind.com";
}

export function isCustomServerUrl(): boolean {
  return !!localStorage.getItem("hivemind_api_url");
}

export function getDefaultApiUrl(): string {
  return import.meta.env.VITE_API_URL || "https://www.thenashlabhivemind.com";
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
  context_documents?: string[];
  context_document_texts?: string[];
  sufficiency_value?: number;
  feasibility_threshold?: number;
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

export interface Recommendation {
  id: string;
  title: string;
  content: string;
  reasoning: string;
  contributing_agents: string[];
  retrieved_chunk_ids: string[];
  feasibility_scores: FeasibilityScore[];
  average_feasibility: number;
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
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface EnterMenuCredentials {
  username: string;
}

// -----------------------------------------------------------------------------
// Token Storage
// -----------------------------------------------------------------------------

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) {
    localStorage.setItem("hivemind_token", token);
  } else {
    localStorage.removeItem("hivemind_token");
  }
}

export function getAuthToken(): string | null {
  if (!authToken) {
    authToken = localStorage.getItem("hivemind_token");
  }
  return authToken;
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
 * 
 * @param req - Analysis request with problem statement and configuration
 * @returns The analysis result with recommendations and audit trail
 */
export async function startAnalysis(req: AnalysisRequest): Promise<AnalysisResult> {
  // Map to the new API format (forward all analysis parameters per DEVELOPMENT_PLAN)
  const payload = {
    problem_statement: req.problem_statement,
    context_documents: req.context_documents ?? [],
    context_document_texts: req.context_document_texts ?? [],
    sufficiency_value: req.sufficiency_value ?? 1,
    feasibility_threshold: req.feasibility_threshold ?? 80,
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
    context_documents: req.context_documents ?? [],
    context_document_texts: req.context_document_texts ?? [],
    sufficiency_value: req.sufficiency_value ?? 1,
    feasibility_threshold: req.feasibility_threshold ?? 80,
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
  // Handle both http->ws and https->wss conversions
  const wsUrl = API_URL.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
  const ws = new WebSocket(`${wsUrl}/ws/analysis/${analysisId}`);

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
      // Try next URL
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
