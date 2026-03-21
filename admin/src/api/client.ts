/**
 * API client for Hivemind Cloud Services.
 * Provides typed methods for all admin operations.
 */

/**
 * API URL - checks localStorage first (set via Settings page), then env var,
 * then falls back to AWS deployment.
 */
const PRODUCTION_API_URL = "http://13.63.209.56:8000";

function normalizeApiUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function getConfiguredApiUrl(): string {
  return normalizeApiUrl(import.meta.env.VITE_API_URL || PRODUCTION_API_URL);
}

function getEffectiveApiUrl(): string {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("hivemind_api_url");
    if (stored) return normalizeApiUrl(stored);
  }
  return getConfiguredApiUrl();
}

let API_URL = getEffectiveApiUrl();

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// -----------------------------------------------------------------------------
// Token Storage
// -----------------------------------------------------------------------------

let authToken: string | null = null;
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
  const token = authToken || localStorage.getItem("hivemind_admin_token");
  if (!token) return;
  const exp = _decodeTokenExp(token);
  if (!exp) return;
  const nowSec = Math.floor(Date.now() / 1000);
  const delayMs = Math.max((exp - nowSec - 300) * 1000, 0);
  _refreshTimer = setTimeout(async () => {
    try {
      const res = await request<{ access_token: string }>("/auth/refresh", {
        method: "POST",
      });
      setAuthToken(res.access_token);
    } catch {
      // Refresh failed — user will need to re-login on next 401
    }
  }, delayMs);
}

export function setAuthToken(token: string | null): void {
  authToken = token;
  if (token) {
    localStorage.setItem("hivemind_admin_token", token);
    _scheduleTokenRefresh();
  } else {
    localStorage.removeItem("hivemind_admin_token");
    if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null; }
  }
}

export function getAuthToken(): string | null {
  if (!authToken) {
    authToken = localStorage.getItem("hivemind_admin_token");
    if (authToken) _scheduleTokenRefresh();
  }
  return authToken;
}

function setActiveApiUrl(url: string, persist = false): string {
  const clean = normalizeApiUrl(url);
  API_URL = clean;
  if (persist && typeof window !== "undefined") {
    localStorage.setItem("hivemind_api_url", clean);
  }
  return clean;
}

/** Change the server URL at runtime (persisted in localStorage). */
export function setServerUrl(url: string): void {
  setActiveApiUrl(url, true);
}

/** Reset to the build-time default URL. */
export function clearServerUrl(): void {
  localStorage.removeItem("hivemind_api_url");
  API_URL = getConfiguredApiUrl();
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
  principles?: string;
  analytical_style?: string;
  scoring_criteria?: string;
  score_interpretation?: string;
  knowledge_base_ids: string[];
  simulation_formula_ids?: string[];
  rag_config: {
    chunks_to_retrieve: number;
    similarity_threshold: number;
    use_reranking: boolean;
  };
  status: "draft" | "published";
  use_case_profile?: string;
  version: number;
  created_by?: string;
}

export interface AgentCreate {
  name: string;
  network_type: "theory" | "practicality";
  description?: string;
  framework?: string;
  principles?: string;
  analytical_style?: string;
  scoring_criteria?: string;
  score_interpretation?: string;
  knowledge_base_ids?: string[];
  simulation_formula_ids?: string[];
  rag_config?: {
    chunks_to_retrieve?: number;
    similarity_threshold?: number;
    use_reranking?: boolean;
  };
  status?: "draft" | "published";
  use_case_profile?: string;
}

export interface SimulationIO {
  name: string;
  description?: string;
  unit?: string;
  default_value?: number | string;
}

export interface Simulation {
  id: string;
  name: string;
  description?: string;
  inputs: SimulationIO[];
  calculations: string;
  outputs: SimulationIO[];
  tags: string[];
  created_by?: string;
}

export interface SimulationCreate {
  name: string;
  description?: string;
  inputs: SimulationIO[];
  calculations: string;
  outputs: SimulationIO[];
  tags?: string[];
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  document_count: number;
  chunk_count: number;
  total_tokens: number;
  embedding_model: string;
  decision_types?: string[];
}

export interface KnowledgeBaseCreate {
  name: string;
  description?: string;
  decision_types?: string[];
}

export interface RetrievedChunk {
  id: string;
  content: string;
  score: number;
  document_name: string;
  source_page?: number;
}

export interface TestResult {
  agent_id: string;
  agent_name: string;
  network_type: string;
  response: string;
  retrieved_chunk_ids: string[];
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
}

export interface SimulationRunResult {
  outputs: Record<string, number | string | null>;
  variables: Record<string, number | string>;
}

// -----------------------------------------------------------------------------
// API Client
// -----------------------------------------------------------------------------

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${path}`;
  const method = (options.method || "GET").toUpperCase();
  console.info(`[Hivemind API] ${method} ${url}`);

  const token = getAuthToken();
  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(url, {
      ...options,
      mode: options.mode ?? "cors",
      credentials: options.credentials ?? "omit",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...options.headers,
      },
    });

    if (!res.ok) {
      const text = await res.text();
      console.error(`[Hivemind API] ${method} ${url} -> ${res.status}`, text);
      throw new Error(`API Error ${res.status}: ${text}`);
    }

    console.info(`[Hivemind API] ${method} ${url} -> ${res.status}`);
    return res.json();
  } catch (error) {
    console.error(
      `[Hivemind API] ${method} ${url} failed: ${describeError(error)}`,
      error
    );
    throw error;
  }
}

// -----------------------------------------------------------------------------
// Authentication
// -----------------------------------------------------------------------------

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  const response = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setAuthToken(response.access_token);
  return response;
}

export function logout(): void {
  setAuthToken(null);
}

// -----------------------------------------------------------------------------
// Agents
// -----------------------------------------------------------------------------

export async function listAgents(): Promise<Agent[]> {
  return request<Agent[]>("/agents");
}

export async function getAgent(id: string): Promise<Agent> {
  return request<Agent>(`/agents/${id}`);
}

export async function createAgent(data: AgentCreate): Promise<Agent> {
  return request<Agent>("/agents", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateAgent(
  id: string,
  data: Partial<AgentCreate>
): Promise<Agent> {
  return request<Agent>(`/agents/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteAgent(id: string): Promise<void> {
  await request(`/agents/${id}`, { method: "DELETE" });
}

export async function publishAgent(
  id: string
): Promise<{ status: string; version: number }> {
  return request(`/agents/${id}/publish`, { method: "POST" });
}

export async function testAgent(
  id: string,
  problem_statement: string
): Promise<TestResult> {
  return request<TestResult>(`/agents/${id}/test`, {
    method: "POST",
    body: JSON.stringify({ problem_statement }),
  });
}

// -----------------------------------------------------------------------------
// Simulations
// -----------------------------------------------------------------------------

export async function listSimulations(): Promise<Simulation[]> {
  return request<Simulation[]>("/simulations");
}

export async function getSimulation(id: string): Promise<Simulation> {
  return request<Simulation>(`/simulations/${id}`);
}

export async function createSimulation(
  data: SimulationCreate
): Promise<Simulation> {
  return request<Simulation>("/simulations", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateSimulation(
  id: string,
  data: Partial<SimulationCreate>
): Promise<Simulation> {
  return request<Simulation>(`/simulations/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteSimulation(id: string): Promise<void> {
  await request(`/simulations/${id}`, { method: "DELETE" });
}

export async function runSimulation(
  id: string,
  inputs: Record<string, number | string>
): Promise<SimulationRunResult> {
  return request<SimulationRunResult>(`/simulations/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });
}

// -----------------------------------------------------------------------------
// Knowledge Bases
// -----------------------------------------------------------------------------

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request<KnowledgeBase[]>("/knowledge-bases");
}

export async function getKnowledgeBase(id: string): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(`/knowledge-bases/${id}`);
}

export async function createKnowledgeBase(
  data: KnowledgeBaseCreate
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>("/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteKnowledgeBase(id: string): Promise<void> {
  await request(`/knowledge-bases/${id}`, { method: "DELETE" });
}

export async function uploadDocument(
  kbId: string,
  file: File
): Promise<{ status: string; document_id: string; chunks: number }> {
  const formData = new FormData();
  formData.append("file", file);

  const uploadHeaders: Record<string, string> = {};
  const uploadToken = getAuthToken();
  if (uploadToken) uploadHeaders["Authorization"] = `Bearer ${uploadToken}`;

  const res = await fetch(`${API_URL}/knowledge-bases/${kbId}/upload`, {
    method: "POST",
    body: formData,
    headers: uploadHeaders,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${text}`);
  }

  return res.json();
}

export async function testRetrieval(
  kbId: string,
  query: string
): Promise<{ results: RetrievedChunk[] }> {
  return request<{ results: RetrievedChunk[] }>(
    `/knowledge-bases/${kbId}/test-retrieval`,
    {
      method: "POST",
      body: JSON.stringify({ query }),
    }
  );
}

// -----------------------------------------------------------------------------
// Upload: Simulation (.py + .txt pair)
// -----------------------------------------------------------------------------

export async function uploadSimulation(
  kbId: string,
  program: File,
  description: File
): Promise<{
  status: string;
  program_document_id: string;
  description_document_id: string;
  chunks: number;
  optimized: boolean;
}> {
  const formData = new FormData();
  formData.append("program", program);
  formData.append("description", description);

  const simHeaders: Record<string, string> = {};
  const simToken = getAuthToken();
  if (simToken) simHeaders["Authorization"] = `Bearer ${simToken}`;

  const res = await fetch(`${API_URL}/knowledge-bases/${kbId}/upload-simulation`, {
    method: "POST",
    body: formData,
    headers: simHeaders,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Simulation upload failed: ${text}`);
  }

  return res.json();
}

// -----------------------------------------------------------------------------
// Upload: Practicality documents
// -----------------------------------------------------------------------------

export async function uploadPracticality(
  kbId: string,
  file: File
): Promise<{ status: string; document_id: string; chunks: number }> {
  const formData = new FormData();
  formData.append("file", file);

  const pracHeaders: Record<string, string> = {};
  const pracToken = getAuthToken();
  if (pracToken) pracHeaders["Authorization"] = `Bearer ${pracToken}`;

  const res = await fetch(`${API_URL}/knowledge-bases/${kbId}/upload-practicality`, {
    method: "POST",
    body: formData,
    headers: pracHeaders,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Practicality upload failed: ${text}`);
  }

  return res.json();
}

// -----------------------------------------------------------------------------
// Upload: Smart auto-classify (AI determines framework vs practicality)
// -----------------------------------------------------------------------------

export async function uploadSmart(
  kbId: string,
  file: File
): Promise<{
  status: string;
  document_id: string;
  document_type: string;
  classified_as: string;
  chunks: number;
  optimized: boolean;
}> {
  const formData = new FormData();
  formData.append("file", file);

  const smartHeaders: Record<string, string> = {};
  const smartToken = getAuthToken();
  if (smartToken) smartHeaders["Authorization"] = `Bearer ${smartToken}`;

  const res = await fetch(`${API_URL}/knowledge-bases/${kbId}/upload-smart`, {
    method: "POST",
    body: formData,
    headers: smartHeaders,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Smart upload failed: ${text}`);
  }

  return res.json();
}

// -----------------------------------------------------------------------------
// Upload: Framework text (paste, no file)
// -----------------------------------------------------------------------------

export async function uploadFrameworkText(
  kbId: string,
  title: string,
  content: string
): Promise<{ status: string; document_id: string; chunks: number; optimized: boolean }> {
  return request(`/knowledge-bases/${kbId}/upload-text`, {
    method: "POST",
    body: JSON.stringify({ title, content }),
  });
}

// -----------------------------------------------------------------------------
// System Theory Agent Management
// -----------------------------------------------------------------------------

export async function syncSystemTheoryAgent(): Promise<void> {
  const kbs = await listKnowledgeBases();
  const agents = await listAgents();
  const systemAgent = agents.find(
    (a) => a.name === "__system_theory__" && a.network_type === "theory"
  );
  const kbIds = kbs.map((kb) => kb.id);

  if (systemAgent) {
    await updateAgent(systemAgent.id, { knowledge_base_ids: kbIds });
    if (systemAgent.status === "draft") {
      await publishAgent(systemAgent.id);
    }
  } else if (kbIds.length > 0) {
    const created = await createAgent({
      name: "__system_theory__",
      network_type: "theory",
      description: "Auto-managed agent for density-based theory unit creation",
      knowledge_base_ids: kbIds,
      framework: "Comprehensive multi-framework analysis",
      principles:
        "Rigorous evidence-based reasoning with diverse analytical perspectives",
      analytical_style: "comprehensive",
      status: "published",
    });
    if (created.status === "draft") {
      await publishAgent(created.id);
    }
  }
}

// -----------------------------------------------------------------------------
// Settings: API Key
// -----------------------------------------------------------------------------

export async function setApiKey(
  apiKey: string
): Promise<{ status: string }> {
  return request<{ status: string }>("/settings/api-key", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function getApiKeyStatus(): Promise<{
  configured: boolean;
  source: string | null;
  masked: string | null;
}> {
  return request("/settings/api-key-status");
}

// -----------------------------------------------------------------------------
// Prompt Preview (local generation for display purposes)
// -----------------------------------------------------------------------------

export function generateTheoryPromptPreview(agent: Partial<AgentCreate>): string {
  const framework = agent.framework || "[framework not set]";
  const principles = agent.principles || "[principles not set]";
  const style = agent.analytical_style || "";

  return `You are ${agent.name || "[name]"}, a strategic analyst specializing in ${framework}. Your approach: ${principles} ${style}.

Your knowledge base:
[RAG chunks will be inserted here based on the query]

Simulation library:
[Attached simulations will be listed here]

When analyzing: apply your framework rigorously, draw from your knowledge base, provide actionable recommendations, support claims with evidence.

When critiquing: identify gaps, note principle conflicts, suggest improvements, acknowledge strengths. If a simulation is helpful, use the formulas and show your inputs and computed outputs explicitly.`;
}

export function generatePracticalityPromptPreview(
  agent: Partial<AgentCreate>
): string {
  const criteria = agent.scoring_criteria || "[criteria not set]";
  const interpretation = agent.score_interpretation || "[interpretation not set]";

  return `You are ${agent.name || "[name]"}, evaluating recommendations for feasibility.

Criteria: ${criteria}

Knowledge base:
[RAG chunks will be inserted here]

Provide: FEASIBILITY SCORE (0-100), KEY RISKS, IMPLEMENTATION CHALLENGES, MITIGATIONS, REASONING.

Score interpretation: ${interpretation}`;
}

// -----------------------------------------------------------------------------
// Health Check & Connection Status
// -----------------------------------------------------------------------------

interface HealthCheckOptions {
  candidateUrl?: string;
  persistSuccess?: boolean;
}

export async function checkServerHealth(
  options: HealthCheckOptions = {}
): Promise<{ status: string; connected: boolean; url?: string }> {
  const primaryUrl = normalizeApiUrl(options.candidateUrl ?? API_URL);
  const uniqueUrls = [primaryUrl];

  for (const url of uniqueUrls) {
    const healthUrl = `${url}/health`;
    console.info(`[Hivemind API] Health check -> ${healthUrl}`);

    try {
      const res = await fetch(healthUrl, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        signal: AbortSignal.timeout(5000),
      });

      if (res.ok) {
        const activeUrl = setActiveApiUrl(url, options.persistSuccess === true);
        if (activeUrl !== primaryUrl) {
          console.warn(
            `[Hivemind API] Primary URL ${primaryUrl} failed; using reachable fallback ${activeUrl}`
          );
        }
        console.info(`[Hivemind API] Health check succeeded via ${activeUrl}`);
        return { status: "connected", connected: true, url: activeUrl };
      }

      const responseBody = await res.text();
      console.error(
        `[Hivemind API] Health check ${healthUrl} -> ${res.status}`,
        responseBody
      );
    } catch (error) {
      console.error(
        `[Hivemind API] Health check failed for ${healthUrl}: ${describeError(error)}`,
        error
      );
    }
  }

  console.error(
    "[Hivemind API] Health check failed for all candidate URLs:",
    uniqueUrls
  );
  return { status: "disconnected", connected: false };
}

export async function pingServer(): Promise<{ status: string; timestamp: number }> {
  return request("/admin/ping", { method: "POST" });
}

export function getApiUrl(): string {
  return API_URL;
}

export function isCustomServerUrl(): boolean {
  return !!localStorage.getItem("hivemind_api_url");
}

export function getDefaultApiUrl(): string {
  return getConfiguredApiUrl();
}

// -----------------------------------------------------------------------------
// Scraped Sources
// -----------------------------------------------------------------------------

export interface ScrapedSource {
  id: string;
  url_or_query: string;
  source_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ScrapedSourceDetail extends ScrapedSource {
  scraped_text: string | null;
}

export async function listScrapedSources(): Promise<ScrapedSource[]> {
  return request<ScrapedSource[]>("/scraped-sources");
}

export async function getScrapedSource(id: string): Promise<ScrapedSourceDetail> {
  return request<ScrapedSourceDetail>(`/scraped-sources/${id}`);
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

export async function deleteScrapedSource(id: string): Promise<void> {
  await request(`/scraped-sources/${id}`, { method: "DELETE" });
}

export async function triggerScrape(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/scraped-sources/${id}/scrape`, {
    method: "POST",
  });
}
