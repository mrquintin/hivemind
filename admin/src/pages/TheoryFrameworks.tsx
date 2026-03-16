import { useEffect, useState, useCallback, useRef } from "react";
import {
  listKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  uploadDocument,
  uploadFrameworkText,
  uploadSmart,
  testRetrieval,
  syncSystemTheoryAgent,
  type KnowledgeBase,
  type RetrievedChunk,
} from "../api/client";

const ACCEPTED_EXTS = [".txt", ".pdf", ".docx", ".doc", ".html"];

export default function TheoryFrameworks() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New KB form
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newDecisionTypes, setNewDecisionTypes] = useState("");
  const [creating, setCreating] = useState(false);

  // Selected KB
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);

  // Framework file upload
  const [uploadingFramework, setUploadingFramework] = useState(false);
  const [frameworkProgress, setFrameworkProgress] = useState("");
  const frameworkInputRef = useRef<HTMLInputElement>(null);

  // Smart upload
  const [uploadingSmart, setUploadingSmart] = useState(false);
  const [smartProgress, setSmartProgress] = useState("");
  const [smartResults, setSmartResults] = useState<
    Array<{ name: string; classified_as: string }>
  >([]);
  const smartInputRef = useRef<HTMLInputElement>(null);

  // Write framework (paste text)
  const [textTitle, setTextTitle] = useState("");
  const [textContent, setTextContent] = useState("");
  const [savingText, setSavingText] = useState(false);

  // Retrieval test
  const [testQuery, setTestQuery] = useState("");
  const [testResults, setTestResults] = useState<RetrievedChunk[]>([]);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listKnowledgeBases();
      setKnowledgeBases(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (selectedKB) {
      const updated = knowledgeBases.find((kb) => kb.id === selectedKB.id);
      if (updated) setSelectedKB(updated);
    }
  }, [knowledgeBases]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      setError("Name is required");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const decision_types = newDecisionTypes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const kb = await createKnowledgeBase({
        name: newName,
        description: newDescription,
        decision_types,
      });
      setKnowledgeBases([...knowledgeBases, kb]);
      setNewName("");
      setNewDescription("");
      setNewDecisionTypes("");
      setShowNewForm(false);
      setSelectedKB(kb);
      // Sync system theory agent with all KBs
      try {
        await syncSystemTheoryAgent();
      } catch {
        /* non-critical */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (
      !confirm(
        `Delete knowledge base "${name}"? This will delete all documents and chunks.`
      )
    )
      return;
    try {
      await deleteKnowledgeBase(id);
      setKnowledgeBases(knowledgeBases.filter((kb) => kb.id !== id));
      if (selectedKB?.id === id) setSelectedKB(null);
      try {
        await syncSystemTheoryAgent();
      } catch {
        /* non-critical */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  // -- Framework file upload --
  const handleFrameworkSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0 || !selectedKB) return;
      setUploadingFramework(true);
      setError(null);
      for (let i = 0; i < files.length; i++) {
        setFrameworkProgress(
          `Uploading & optimizing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          await uploadDocument(selectedKB.id, files[i]);
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setUploadingFramework(false);
      setFrameworkProgress("");
      await load();
      if (frameworkInputRef.current) frameworkInputRef.current.value = "";
    },
    [selectedKB]
  );

  const handleFrameworkDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      if (!selectedKB) return;
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        ACCEPTED_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
      );
      if (files.length === 0) {
        setError("Only .txt, .pdf, .docx, and .html files are accepted");
        return;
      }
      setUploadingFramework(true);
      setError(null);
      for (let i = 0; i < files.length; i++) {
        setFrameworkProgress(
          `Uploading & optimizing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          await uploadDocument(selectedKB.id, files[i]);
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setUploadingFramework(false);
      setFrameworkProgress("");
      await load();
    },
    [selectedKB]
  );

  // -- Smart upload --
  const handleSmartSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0 || !selectedKB) return;
      setUploadingSmart(true);
      setError(null);
      const results: Array<{ name: string; classified_as: string }> = [];
      for (let i = 0; i < files.length; i++) {
        setSmartProgress(
          `Classifying & processing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          const result = await uploadSmart(selectedKB.id, files[i]);
          results.push({ name: files[i].name, classified_as: result.classified_as });
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setSmartResults(results);
      setUploadingSmart(false);
      setSmartProgress("");
      await load();
      if (smartInputRef.current) smartInputRef.current.value = "";
    },
    [selectedKB]
  );

  const handleSmartDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      if (!selectedKB) return;
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        ACCEPTED_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
      );
      if (files.length === 0) {
        setError("Only .txt, .pdf, .docx, and .html files are accepted");
        return;
      }
      setUploadingSmart(true);
      setError(null);
      const results: Array<{ name: string; classified_as: string }> = [];
      for (let i = 0; i < files.length; i++) {
        setSmartProgress(
          `Classifying & processing ${files[i].name} (${i + 1}/${files.length})...`
        );
        try {
          const result = await uploadSmart(selectedKB.id, files[i]);
          results.push({ name: files[i].name, classified_as: result.classified_as });
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed: ${files[i].name}`
          );
        }
      }
      setSmartResults(results);
      setUploadingSmart(false);
      setSmartProgress("");
      await load();
    },
    [selectedKB]
  );

  // -- Write framework text --
  const handleSaveText = async () => {
    if (!selectedKB || !textContent.trim()) return;
    setSavingText(true);
    setError(null);
    try {
      await uploadFrameworkText(
        selectedKB.id,
        textTitle.trim() || "Untitled Framework",
        textContent
      );
      setTextTitle("");
      setTextContent("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save text");
    } finally {
      setSavingText(false);
    }
  };

  // -- Test retrieval --
  const handleTestRetrieval = async () => {
    if (!selectedKB || !testQuery.trim()) return;
    setTesting(true);
    setError(null);
    try {
      const result = await testRetrieval(selectedKB.id, testQuery);
      setTestResults(result.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retrieval test failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Theory Frameworks</h1>
          <p className="page-subtitle">
            Upload and manage analytical frameworks, algorithms, and
            methodologies for the theory network
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowNewForm(true)}
        >
          + New Knowledge Base
        </button>
      </header>

      {error && <div className="error-message">{error}</div>}

      <div className="page-content kb-layout">
        {/* KB List Panel */}
        <div className="kb-list-panel">
          {showNewForm && (
            <div className="card new-kb-form">
              <h3>Create Knowledge Base</h3>
              <div className="form-group">
                <label className="form-label">Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., Financial Analysis Frameworks"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea
                  className="form-textarea"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="What frameworks will this base contain?"
                  rows={2}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Decision types</label>
                <input
                  type="text"
                  className="form-input"
                  value={newDecisionTypes}
                  onChange={(e) => setNewDecisionTypes(e.target.value)}
                  placeholder="e.g., market_entry, m_and_a, pricing"
                />
                <span className="form-hint">
                  Comma-separated. Used to match knowledge bases to client
                  analysis requests.
                </span>
              </div>
              <div className="button-group">
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowNewForm(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleCreate}
                  disabled={creating}
                >
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="loading">Loading...</div>
          ) : knowledgeBases.length === 0 ? (
            <div className="empty-state">
              No knowledge bases yet. Create one to get started.
            </div>
          ) : (
            <ul className="kb-list">
              {knowledgeBases.map((kb) => (
                <li
                  key={kb.id}
                  className={`kb-item ${selectedKB?.id === kb.id ? "selected" : ""}`}
                  onClick={() => {
                    setSelectedKB(kb);
                    setTestResults([]);
                    setTestQuery("");
                    setSmartResults([]);
                  }}
                >
                  <div className="kb-item-name">{kb.name}</div>
                  <div className="kb-item-meta">
                    {kb.document_count} docs · {kb.chunk_count} chunks
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Detail Panel */}
        <div className="kb-detail-panel">
          {selectedKB ? (
            <>
              {/* Stats */}
              <div className="card">
                <div className="card-header">
                  <h2 className="card-title">{selectedKB.name}</h2>
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() =>
                      handleDelete(selectedKB.id, selectedKB.name)
                    }
                  >
                    Delete
                  </button>
                </div>
                {selectedKB.description && (
                  <p className="kb-description">{selectedKB.description}</p>
                )}
                <div className="kb-stats">
                  <div className="stat">
                    <span className="stat-value">
                      {selectedKB.document_count}
                    </span>
                    <span className="stat-label">Documents</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">
                      {selectedKB.chunk_count}
                    </span>
                    <span className="stat-label">Chunks</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">
                      {(selectedKB.total_tokens / 1000).toFixed(1)}k
                    </span>
                    <span className="stat-label">Tokens</span>
                  </div>
                </div>
              </div>

              {/* Upload Documents */}
              <div
                className={`card upload-zone ${uploadingFramework ? "uploading" : ""}`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleFrameworkDrop}
              >
                <h3>Upload Framework Documents</h3>
                <p className="hint">
                  Upload one document per theory/framework. AI automatically
                  extracts and optimizes content for RAG precision. Supports
                  .txt, .pdf, .docx, .html.
                </p>
                <input
                  ref={frameworkInputRef}
                  type="file"
                  multiple
                  accept=".txt,.pdf,.docx,.doc,.html"
                  onChange={handleFrameworkSelect}
                  className="file-input"
                />
                <button
                  className="btn btn-primary"
                  onClick={() => frameworkInputRef.current?.click()}
                  disabled={uploadingFramework}
                >
                  {uploadingFramework ? frameworkProgress : "Select Files"}
                </button>
                <p className="hint small">
                  Drag & drop files here, or click to browse
                </p>
              </div>

              {/* Write Framework (paste text) */}
              <div className="card">
                <h3>Write Framework</h3>
                <p className="hint">
                  Write or paste a framework description directly. One
                  theory/framework per entry. AI optimizes for RAG retrieval.
                </p>
                <div className="form-group">
                  <label className="form-label">Title</label>
                  <input
                    type="text"
                    className="form-input"
                    value={textTitle}
                    onChange={(e) => setTextTitle(e.target.value)}
                    placeholder="e.g., Porter's Five Forces Analysis"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Content</label>
                  <textarea
                    className="form-textarea"
                    value={textContent}
                    onChange={(e) => setTextContent(e.target.value)}
                    placeholder="Paste or write the framework description here..."
                    rows={10}
                  />
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveText}
                  disabled={savingText || !textContent.trim()}
                >
                  {savingText ? "Saving & Optimizing..." : "Save Framework"}
                </button>
              </div>

              {/* Smart Upload */}
              <div
                className={`card upload-zone ${uploadingSmart ? "uploading" : ""}`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleSmartDrop}
              >
                <h3>Smart Upload (AI Auto-Classify)</h3>
                <p className="hint">
                  Drop any document here. AI classifies it as framework or
                  practicality and optimizes accordingly.
                </p>
                <input
                  ref={smartInputRef}
                  type="file"
                  multiple
                  accept=".txt,.pdf,.docx,.doc,.html"
                  onChange={handleSmartSelect}
                  className="file-input"
                />
                <button
                  className="btn btn-secondary"
                  onClick={() => smartInputRef.current?.click()}
                  disabled={uploadingSmart}
                >
                  {uploadingSmart
                    ? smartProgress
                    : "Select Files (Auto-Classify)"}
                </button>
                {smartResults.length > 0 && (
                  <div style={{ marginTop: "12px", textAlign: "left" }}>
                    <p
                      className="hint"
                      style={{ marginTop: 0, marginBottom: "8px" }}
                    >
                      Classification results:
                    </p>
                    {smartResults.map((r, idx) => (
                      <div
                        key={idx}
                        style={{ fontSize: "13px", marginBottom: "4px" }}
                      >
                        <span style={{ color: "var(--text-secondary)" }}>
                          {r.name}
                        </span>
                        {" \u2192 "}
                        <span
                          style={{
                            color:
                              r.classified_as === "practicality"
                                ? "var(--warn, #e8a838)"
                                : "var(--primary, #4a9eff)",
                            fontWeight: 500,
                          }}
                        >
                          {r.classified_as}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Test Retrieval */}
              <div className="card">
                <h3>Test Retrieval</h3>
                <p className="hint">
                  Enter a query to test which knowledge chunks would be
                  retrieved during an analysis.
                </p>
                <div className="form-group">
                  <textarea
                    className="form-textarea"
                    value={testQuery}
                    onChange={(e) => setTestQuery(e.target.value)}
                    placeholder="What is the optimal pricing strategy for a new market entry?"
                    rows={2}
                  />
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleTestRetrieval}
                  disabled={testing || !testQuery.trim()}
                >
                  {testing ? "Searching..." : "Search"}
                </button>
                {testResults.length > 0 && (
                  <div className="retrieval-results">
                    <h4>Results ({testResults.length} chunks)</h4>
                    {testResults.map((chunk, idx) => (
                      <div key={chunk.id} className="chunk-result">
                        <div className="chunk-header">
                          <span className="chunk-rank">#{idx + 1}</span>
                          <span className="chunk-source">
                            {chunk.document_name}
                            {chunk.source_page && ` (p${chunk.source_page})`}
                          </span>
                          <span className="chunk-score">
                            {(chunk.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="chunk-content">{chunk.content}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              Select a knowledge base to upload frameworks and test retrieval
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
