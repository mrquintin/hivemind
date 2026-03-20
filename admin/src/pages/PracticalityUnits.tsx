import { useEffect, useState, useCallback, useRef } from "react";
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  publishAgent,
  testAgent,
  listKnowledgeBases,
  createKnowledgeBase,
  uploadPracticality,
  generatePracticalityPromptPreview,
  type Agent,
  type AgentCreate,
  type KnowledgeBase,
  type TestResult,
} from "../api/client";

const ACCEPTED_EXTS = [".txt", ".pdf", ".docx", ".doc", ".html"];

const DEFAULT_RAG_CONFIG = {
  chunks_to_retrieve: 5,
  similarity_threshold: 0.7,
  use_reranking: false,
};

export default function PracticalityUnits() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selected agent
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isNew, setIsNew] = useState(false);

  // Form
  const [form, setForm] = useState<AgentCreate>({
    name: "",
    network_type: "practicality",
    description: "",
    scoring_criteria: "",
    score_interpretation: "",
    knowledge_base_ids: [],
    rag_config: DEFAULT_RAG_CONFIG,
    status: "draft",
    use_case_profile: "",
  });

  const [saving, setSaving] = useState(false);

  // Inline KB creation
  const [showNewKB, setShowNewKB] = useState(false);
  const [newKbName, setNewKbName] = useState("");
  const [newKbDesc, setNewKbDesc] = useState("");
  const [creatingKB, setCreatingKB] = useState(false);

  // Practicality doc upload
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const docInputRef = useRef<HTMLInputElement>(null);

  // Prompt preview
  const [showPreview, setShowPreview] = useState(false);

  // Test
  const [testQuery, setTestQuery] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [allAgents, kbs] = await Promise.all([
        listAgents(),
        listKnowledgeBases(),
      ]);
      // Only show practicality agents (exclude system theory agent)
      setAgents(
        allAgents.filter(
          (a) =>
            a.network_type === "practicality" &&
            a.name !== "__system_theory__"
        )
      );
      setKnowledgeBases(kbs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openNew = () => {
    setSelectedAgent(null);
    setIsNew(true);
    setForm({
      name: "",
      network_type: "practicality",
      description: "",
      scoring_criteria: "",
      score_interpretation: "",
      knowledge_base_ids: [],
      rag_config: DEFAULT_RAG_CONFIG,
      status: "draft",
      use_case_profile: "",
    });
    setTestQuery("");
    setTestResult(null);
  };

  const openEdit = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsNew(false);
    setForm({
      name: agent.name,
      network_type: "practicality",
      description: agent.description || "",
      scoring_criteria: agent.scoring_criteria || "",
      score_interpretation: agent.score_interpretation || "",
      knowledge_base_ids: agent.knowledge_base_ids || [],
      rag_config: agent.rag_config || DEFAULT_RAG_CONFIG,
      status: agent.status,
      use_case_profile: agent.use_case_profile || "",
    });
    setTestQuery("");
    setTestResult(null);
  };

  const handleChange = useCallback(
    (
      field: keyof AgentCreate,
      value: string | string[] | number | boolean
    ) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const handleRagChange = useCallback(
    (field: keyof typeof DEFAULT_RAG_CONFIG, value: number | boolean) => {
      setForm((prev) => ({
        ...prev,
        rag_config: { ...prev.rag_config!, [field]: value },
      }));
    },
    []
  );

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError("Unit name is required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (isNew) {
        const agent = await createAgent(form);
        setSelectedAgent(agent);
        setIsNew(false);
        await load();
      } else if (selectedAgent) {
        await updateAgent(selectedAgent.id, form);
        await load();
        // Refresh selected agent
        const allAgents = await listAgents();
        const updated = allAgents.find((a) => a.id === selectedAgent.id);
        if (updated) setSelectedAgent(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!selectedAgent) return;
    try {
      await publishAgent(selectedAgent.id);
      await load();
      const allAgents = await listAgents();
      const updated = allAgents.find((a) => a.id === selectedAgent.id);
      if (updated) {
        setSelectedAgent(updated);
        setForm((prev) => ({ ...prev, status: "published" }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish");
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete unit "${name}"?`)) return;
    try {
      await deleteAgent(id);
      if (selectedAgent?.id === id) {
        setSelectedAgent(null);
        setIsNew(false);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  // -- Inline KB creation --
  const handleCreateKB = async () => {
    if (!newKbName.trim()) return;
    setCreatingKB(true);
    try {
      const kb = await createKnowledgeBase({
        name: newKbName,
        description: newKbDesc,
      });
      setKnowledgeBases([...knowledgeBases, kb]);
      // Auto-select the new KB
      handleChange("knowledge_base_ids", [
        ...(form.knowledge_base_ids || []),
        kb.id,
      ]);
      setNewKbName("");
      setNewKbDesc("");
      setShowNewKB(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create KB");
    } finally {
      setCreatingKB(false);
    }
  };

  // -- Practicality doc upload --
  const handleDocSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const kbIds = form.knowledge_base_ids || [];
      if (kbIds.length === 0) {
        setError("Select a knowledge base first");
        return;
      }
      setUploadingDoc(true);
      setError(null);
      for (let i = 0; i < files.length; i++) {
        setUploadProgress(
          `Uploading & optimizing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          // Upload to each selected KB
          for (const kbId of kbIds) {
            await uploadPracticality(kbId, files[i]);
          }
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setUploadingDoc(false);
      setUploadProgress("");
      await load();
      if (docInputRef.current) docInputRef.current.value = "";
    },
    [form.knowledge_base_ids]
  );

  const handleDocDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      const kbIds = form.knowledge_base_ids || [];
      if (kbIds.length === 0) {
        setError("Select a knowledge base first");
        return;
      }
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        ACCEPTED_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
      );
      if (files.length === 0) {
        setError("Only .txt, .pdf, .docx, and .html files are accepted");
        return;
      }
      setUploadingDoc(true);
      setError(null);
      for (let i = 0; i < files.length; i++) {
        setUploadProgress(
          `Uploading & optimizing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          for (const kbId of kbIds) {
            await uploadPracticality(kbId, files[i]);
          }
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setUploadingDoc(false);
      setUploadProgress("");
      await load();
    },
    [form.knowledge_base_ids]
  );

  // -- Test agent --
  const handleTest = async () => {
    if (!selectedAgent || !testQuery.trim()) return;
    setTesting(true);
    setError(null);
    try {
      const result = await testAgent(selectedAgent.id, testQuery);
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  };

  const promptPreview = generatePracticalityPromptPreview(form);

  // Get stats for selected KBs
  const selectedKBStats = knowledgeBases.filter((kb) =>
    (form.knowledge_base_ids || []).includes(kb.id)
  );
  const totalDocs = selectedKBStats.reduce(
    (sum, kb) => sum + kb.document_count,
    0
  );
  const totalChunks = selectedKBStats.reduce(
    (sum, kb) => sum + kb.chunk_count,
    0
  );
  const totalTokens = selectedKBStats.reduce(
    (sum, kb) => sum + kb.total_tokens,
    0
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Practicality Units</h1>
          <p className="page-subtitle">
            Create and manage feasibility-scoring AI units for the practicality
            network
          </p>
        </div>
        <button className="btn btn-primary" onClick={openNew}>
          + New Unit
        </button>
      </header>

      {error && <div className="error-message">{error}</div>}

      <div className="page-content kb-layout">
        {/* Unit List */}
        <div className="kb-list-panel">
          {loading ? (
            <div className="loading">Loading...</div>
          ) : agents.length === 0 ? (
            <div className="empty-state">
              No practicality units yet. Create one to get started.
            </div>
          ) : (
            <ul className="kb-list">
              {agents.map((agent) => (
                <li
                  key={agent.id}
                  className={`kb-item ${selectedAgent?.id === agent.id ? "selected" : ""}`}
                  onClick={() => openEdit(agent)}
                >
                  <div className="kb-item-name">
                    {agent.name}
                    <span
                      className={`status-badge ${agent.status}`}
                      style={{
                        marginLeft: "8px",
                        fontSize: "11px",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        backgroundColor:
                          agent.status === "published"
                            ? "var(--success, #22c55e)"
                            : "var(--warn, #e8a838)",
                        color: "#fff",
                      }}
                    >
                      {agent.status}
                    </span>
                  </div>
                  <div className="kb-item-meta">
                    {agent.knowledge_base_ids.length} KBs · v{agent.version}
                    {agent.use_case_profile && ` · ${agent.use_case_profile}`}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right Panel: Editor */}
        <div className="kb-detail-panel">
          {selectedAgent || isNew ? (
            <>
              {/* Unit Configuration */}
              <div className="card">
                <div className="card-header">
                  <h2 className="card-title">
                    {isNew ? "New Practicality Unit" : selectedAgent?.name}
                  </h2>
                  <div className="button-group">
                    {selectedAgent && (
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() =>
                          handleDelete(selectedAgent.id, selectedAgent.name)
                        }
                      >
                        Delete
                      </button>
                    )}
                    {selectedAgent && selectedAgent.status === "draft" && (
                      <button
                        className="btn btn-small"
                        onClick={handlePublish}
                        style={{
                          backgroundColor: "var(--success, #22c55e)",
                          color: "#fff",
                        }}
                      >
                        Publish
                      </button>
                    )}
                    <button
                      className="btn btn-primary"
                      onClick={handleSave}
                      disabled={saving}
                    >
                      {saving ? "Saving..." : "Save"}
                    </button>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={(e) => handleChange("name", e.target.value)}
                    placeholder="e.g., Regulatory Compliance Scorer"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    className="form-textarea"
                    value={form.description}
                    onChange={(e) =>
                      handleChange("description", e.target.value)
                    }
                    placeholder="What does this unit evaluate?"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Use-case Profile</label>
                  <select
                    className="form-select"
                    value={form.use_case_profile ?? ""}
                    onChange={(e) =>
                      handleChange("use_case_profile", e.target.value)
                    }
                  >
                    <option value="">-- None --</option>
                    <option value="small_business">Small Business</option>
                    <option value="individual_career">
                      Individual / Career
                    </option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Scoring Criteria</label>
                  <textarea
                    className="form-textarea"
                    value={form.scoring_criteria}
                    onChange={(e) =>
                      handleChange("scoring_criteria", e.target.value)
                    }
                    placeholder="Define what criteria this unit uses to score feasibility..."
                    rows={4}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Score Interpretation</label>
                  <textarea
                    className="form-textarea"
                    value={form.score_interpretation}
                    onChange={(e) =>
                      handleChange("score_interpretation", e.target.value)
                    }
                    placeholder="e.g., 0-30: Not feasible, 30-70: Feasible with modifications, 70-100: Highly feasible"
                    rows={3}
                  />
                </div>
              </div>

              {/* RAG Config */}
              <div className="card">
                <h3>RAG Configuration</h3>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Chunks to Retrieve</label>
                    <input
                      type="number"
                      className="form-input"
                      value={form.rag_config?.chunks_to_retrieve || 5}
                      onChange={(e) =>
                        handleRagChange(
                          "chunks_to_retrieve",
                          parseInt(e.target.value)
                        )
                      }
                      min={1}
                      max={20}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Similarity Threshold</label>
                    <input
                      type="number"
                      className="form-input"
                      value={form.rag_config?.similarity_threshold || 0.7}
                      onChange={(e) =>
                        handleRagChange(
                          "similarity_threshold",
                          parseFloat(e.target.value)
                        )
                      }
                      min={0}
                      max={1}
                      step={0.05}
                    />
                  </div>
                </div>
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={form.rag_config?.use_reranking || false}
                    onChange={(e) =>
                      handleRagChange("use_reranking", e.target.checked)
                    }
                  />
                  <span className="checkbox-label">Use reranking</span>
                </label>
              </div>

              {/* Knowledge Base */}
              <div className="card">
                <div className="card-header">
                  <h3>Knowledge Base</h3>
                  <button
                    className="btn btn-small"
                    onClick={() => setShowNewKB(!showNewKB)}
                  >
                    {showNewKB ? "Cancel" : "+ New KB"}
                  </button>
                </div>
                <p className="hint">
                  Select knowledge bases containing feasibility constraints,
                  risk frameworks, and scoring benchmarks.
                </p>

                {showNewKB && (
                  <div
                    style={{
                      padding: "12px",
                      border: "1px solid var(--border)",
                      borderRadius: "6px",
                      marginBottom: "12px",
                    }}
                  >
                    <div className="form-group">
                      <label className="form-label">KB Name *</label>
                      <input
                        type="text"
                        className="form-input"
                        value={newKbName}
                        onChange={(e) => setNewKbName(e.target.value)}
                        placeholder="e.g., Regulatory Constraints"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Description</label>
                      <input
                        type="text"
                        className="form-input"
                        value={newKbDesc}
                        onChange={(e) => setNewKbDesc(e.target.value)}
                        placeholder="What constraints does it contain?"
                      />
                    </div>
                    <button
                      className="btn btn-primary"
                      onClick={handleCreateKB}
                      disabled={creatingKB || !newKbName.trim()}
                    >
                      {creatingKB ? "Creating..." : "Create KB"}
                    </button>
                  </div>
                )}

                {knowledgeBases.length === 0 ? (
                  <div className="empty-state">
                    No knowledge bases available.
                  </div>
                ) : (
                  <div className="checkbox-list">
                    {knowledgeBases.map((kb) => (
                      <label key={kb.id} className="checkbox-item">
                        <input
                          type="checkbox"
                          checked={(form.knowledge_base_ids || []).includes(
                            kb.id
                          )}
                          onChange={(e) => {
                            const ids = form.knowledge_base_ids || [];
                            handleChange(
                              "knowledge_base_ids",
                              e.target.checked
                                ? [...ids, kb.id]
                                : ids.filter((i) => i !== kb.id)
                            );
                          }}
                        />
                        <span className="checkbox-label">
                          {kb.name}
                          <span className="checkbox-meta">
                            {kb.document_count} docs, {kb.chunk_count} chunks
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}

                {(form.knowledge_base_ids || []).length > 0 && (
                  <div className="kb-stats" style={{ marginTop: "12px" }}>
                    <div className="stat">
                      <span className="stat-value">{totalDocs}</span>
                      <span className="stat-label">Docs</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{totalChunks}</span>
                      <span className="stat-label">Chunks</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">
                        {(totalTokens / 1000).toFixed(1)}k
                      </span>
                      <span className="stat-label">Tokens</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Upload Practicality Documents */}
              {(form.knowledge_base_ids || []).length > 0 && (
                <div
                  className={`card upload-zone ${uploadingDoc ? "uploading" : ""}`}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDocDrop}
                >
                  <h3>Upload Practicality Documents</h3>
                  <p className="hint">
                    Upload constraints, scoring criteria, risk frameworks for
                    this unit's knowledge base. Supports .txt, .pdf, .docx,
                    .html.
                  </p>
                  <input
                    ref={docInputRef}
                    type="file"
                    multiple
                    accept=".txt,.pdf,.docx,.doc,.html"
                    onChange={handleDocSelect}
                    className="file-input"
                  />
                  <button
                    className="btn btn-primary"
                    onClick={() => docInputRef.current?.click()}
                    disabled={uploadingDoc}
                  >
                    {uploadingDoc ? uploadProgress : "Select Files"}
                  </button>
                  <p className="hint small">
                    Drag & drop files here. AI optimizes for
                    constraint/feasibility retrieval.
                  </p>
                </div>
              )}

              {/* Prompt Preview */}
              <div className="card">
                <div className="card-header">
                  <h3>Prompt Preview</h3>
                  <button
                    className="btn btn-small"
                    onClick={() => setShowPreview(!showPreview)}
                  >
                    {showPreview ? "Hide" : "Show"}
                  </button>
                </div>
                {showPreview && (
                  <pre className="prompt-preview">{promptPreview}</pre>
                )}
              </div>

              {/* Test Unit */}
              {selectedAgent && selectedAgent.status === "published" && (
                <div className="card">
                  <h3>Test Unit</h3>
                  <div className="form-group">
                    <label className="form-label">Problem Statement</label>
                    <textarea
                      className="form-textarea"
                      value={testQuery}
                      onChange={(e) => setTestQuery(e.target.value)}
                      placeholder="Enter a recommendation to evaluate for feasibility..."
                      rows={3}
                    />
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={handleTest}
                    disabled={testing || !testQuery.trim()}
                  >
                    {testing ? "Running..." : "Run Test"}
                  </button>
                  {testResult && (
                    <div className="test-result">
                      <h4>Result</h4>
                      <div className="test-meta">
                        <span>Input: {testResult.input_tokens} tokens</span>
                        <span>Output: {testResult.output_tokens} tokens</span>
                        <span>Latency: {testResult.latency_ms}ms</span>
                      </div>
                      <pre className="test-response">{testResult.response}</pre>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              Select a unit to edit, or create a new one
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
