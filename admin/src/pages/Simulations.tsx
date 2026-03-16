import { useEffect, useState, useCallback, useRef } from "react";
import {
  listSimulations,
  getSimulation,
  createSimulation,
  updateSimulation,
  deleteSimulation,
  runSimulation,
  listKnowledgeBases,
  uploadSimulation,
  type Simulation,
  type SimulationCreate,
  type SimulationIO,
  type SimulationRunResult,
  type KnowledgeBase,
} from "../api/client";

const EMPTY_IO: SimulationIO = {
  name: "",
  description: "",
  unit: "",
  default_value: "",
};

type View = "list" | "upload" | "detail" | "edit";

export default function Simulations() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selected simulation
  const [selectedSim, setSelectedSim] = useState<Simulation | null>(null);
  const [view, setView] = useState<View>("list");

  // Upload simulation state
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [uploadKbId, setUploadKbId] = useState("");
  const [simProgram, setSimProgram] = useState<File | null>(null);
  const [simDesc, setSimDesc] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const simProgramRef = useRef<HTMLInputElement>(null);
  const simDescRef = useRef<HTMLInputElement>(null);

  // Create/edit form
  const [form, setForm] = useState<SimulationCreate>({
    name: "",
    description: "",
    inputs: [{ ...EMPTY_IO }],
    calculations:
      "# Write Python-style calculations\n# Use input variable names directly\n# Assign to output variable names\n\n",
    outputs: [{ ...EMPTY_IO }],
    tags: [],
  });
  const [tagInput, setTagInput] = useState("");
  const [saving, setSaving] = useState(false);

  // Test state
  const [testInputs, setTestInputs] = useState<Record<string, string>>({});
  const [testResult, setTestResult] = useState<SimulationRunResult | null>(
    null
  );
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [sims, kbs] = await Promise.all([
        listSimulations(),
        listKnowledgeBases(),
      ]);
      setSimulations(sims);
      setKnowledgeBases(kbs);
      if (kbs.length > 0 && !uploadKbId) setUploadKbId(kbs[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete simulation "${name}"?`)) return;
    try {
      await deleteSimulation(id);
      setSimulations(simulations.filter((s) => s.id !== id));
      if (selectedSim?.id === id) {
        setSelectedSim(null);
        setView("list");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  // -- Upload simulation pair --
  const handleSimUpload = useCallback(async () => {
    if (!uploadKbId || !simProgram || !simDesc) return;
    setUploading(true);
    setUploadProgress("Uploading simulation pair & optimizing description...");
    setError(null);
    try {
      await uploadSimulation(uploadKbId, simProgram, simDesc);
      setSimProgram(null);
      setSimDesc(null);
      if (simProgramRef.current) simProgramRef.current.value = "";
      if (simDescRef.current) simDescRef.current.value = "";
      setUploadProgress("Upload complete!");
      await load();
      setTimeout(() => setUploadProgress(""), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploadProgress("");
    } finally {
      setUploading(false);
    }
  }, [uploadKbId, simProgram, simDesc]);

  // -- Form handlers --
  const handleChange = useCallback(
    (field: keyof SimulationCreate, value: string | string[]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const handleIOChange = useCallback(
    (
      type: "inputs" | "outputs",
      index: number,
      field: keyof SimulationIO,
      value: string | number
    ) => {
      setForm((prev) => ({
        ...prev,
        [type]: prev[type].map((item, i) =>
          i === index ? { ...item, [field]: value } : item
        ),
      }));
    },
    []
  );

  const addIO = useCallback((type: "inputs" | "outputs") => {
    setForm((prev) => ({
      ...prev,
      [type]: [...prev[type], { ...EMPTY_IO }],
    }));
  }, []);

  const removeIO = useCallback((type: "inputs" | "outputs", index: number) => {
    setForm((prev) => ({
      ...prev,
      [type]: prev[type].filter((_, i) => i !== index),
    }));
  }, []);

  const addTag = useCallback(() => {
    if (tagInput.trim() && !form.tags?.includes(tagInput.trim())) {
      setForm((prev) => ({
        ...prev,
        tags: [...(prev.tags || []), tagInput.trim()],
      }));
      setTagInput("");
    }
  }, [tagInput, form.tags]);

  const removeTag = useCallback((tag: string) => {
    setForm((prev) => ({
      ...prev,
      tags: (prev.tags || []).filter((t) => t !== tag),
    }));
  }, []);

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError("Simulation name is required");
      return;
    }
    if (!form.calculations.trim()) {
      setError("Calculations are required");
      return;
    }
    const data = {
      ...form,
      inputs: form.inputs.filter((i) => i.name.trim()),
      outputs: form.outputs.filter((o) => o.name.trim()),
    };
    setSaving(true);
    setError(null);
    try {
      if (selectedSim) {
        await updateSimulation(selectedSim.id, data);
        await load();
        // Re-select to refresh
        const updated = await getSimulation(selectedSim.id);
        setSelectedSim(updated);
        setView("detail");
      } else {
        const sim = await createSimulation(data);
        await load();
        setSelectedSim(sim);
        setView("detail");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!selectedSim) return;
    const inputs: Record<string, number | string> = {};
    form.inputs.forEach((inp) => {
      const val = testInputs[inp.name];
      const num = parseFloat(val);
      inputs[inp.name] = isNaN(num) ? val : num;
    });
    setTesting(true);
    setError(null);
    try {
      const result = await runSimulation(selectedSim.id, inputs);
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  };

  const openEdit = (sim: Simulation) => {
    setSelectedSim(sim);
    setForm({
      name: sim.name,
      description: sim.description || "",
      inputs: sim.inputs.length > 0 ? sim.inputs : [{ ...EMPTY_IO }],
      calculations: sim.calculations,
      outputs: sim.outputs.length > 0 ? sim.outputs : [{ ...EMPTY_IO }],
      tags: sim.tags || [],
    });
    const defaults: Record<string, string> = {};
    sim.inputs.forEach((inp) => {
      defaults[inp.name] = String(inp.default_value || "");
    });
    setTestInputs(defaults);
    setTestResult(null);
    setView("edit");
  };

  const openDetail = (sim: Simulation) => {
    setSelectedSim(sim);
    setForm({
      name: sim.name,
      description: sim.description || "",
      inputs: sim.inputs.length > 0 ? sim.inputs : [{ ...EMPTY_IO }],
      calculations: sim.calculations,
      outputs: sim.outputs.length > 0 ? sim.outputs : [{ ...EMPTY_IO }],
      tags: sim.tags || [],
    });
    const defaults: Record<string, string> = {};
    sim.inputs.forEach((inp) => {
      defaults[inp.name] = String(inp.default_value || "");
    });
    setTestInputs(defaults);
    setTestResult(null);
    setView("detail");
  };

  const openNewForm = () => {
    setSelectedSim(null);
    setForm({
      name: "",
      description: "",
      inputs: [{ ...EMPTY_IO }],
      calculations:
        "# Write Python-style calculations\n# Use input variable names directly\n# Assign to output variable names\n\n",
      outputs: [{ ...EMPTY_IO }],
      tags: [],
    });
    setTagInput("");
    setTestInputs({});
    setTestResult(null);
    setView("edit");
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Simulations</h1>
          <p className="page-subtitle">
            Upload Python programs or create formula-based simulations for
            theory network analysis
          </p>
        </div>
        <div className="button-group">
          <button
            className="btn btn-secondary"
            onClick={() => setView("upload")}
          >
            Upload Simulation
          </button>
          <button className="btn btn-primary" onClick={openNewForm}>
            + Create Formula
          </button>
        </div>
      </header>

      {error && <div className="error-message">{error}</div>}

      <div className="page-content kb-layout">
        {/* Simulation List */}
        <div className="kb-list-panel">
          {loading ? (
            <div className="loading">Loading...</div>
          ) : simulations.length === 0 ? (
            <div className="empty-state">
              No simulations yet. Upload or create one to get started.
            </div>
          ) : (
            <ul className="kb-list">
              {simulations.map((sim) => (
                <li
                  key={sim.id}
                  className={`kb-item ${selectedSim?.id === sim.id ? "selected" : ""}`}
                  onClick={() => openDetail(sim)}
                >
                  <div className="kb-item-name">{sim.name}</div>
                  <div className="kb-item-meta">
                    {sim.inputs.length} inputs · {sim.outputs.length} outputs
                    {sim.tags.length > 0 && (
                      <>
                        {" · "}
                        {sim.tags.slice(0, 2).join(", ")}
                        {sim.tags.length > 2 && "..."}
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right Panel */}
        <div className="kb-detail-panel">
          {/* Upload View */}
          {view === "upload" && (
            <>
              <div className={`card upload-zone ${uploading ? "uploading" : ""}`}>
                <h3>Upload Simulation Program</h3>
                <p className="hint">
                  Upload a Python simulation program (.py) and a companion
                  document describing its inputs, outputs, and usage. PDFs and
                  other documents are automatically converted to text.
                </p>

                {knowledgeBases.length > 0 && (
                  <div className="form-group">
                    <label className="form-label">Target Knowledge Base</label>
                    <select
                      className="form-select"
                      value={uploadKbId}
                      onChange={(e) => setUploadKbId(e.target.value)}
                    >
                      {knowledgeBases.map((kb) => (
                        <option key={kb.id} value={kb.id}>
                          {kb.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div
                  style={{
                    display: "flex",
                    gap: "12px",
                    marginBottom: "12px",
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <label className="form-label">.py Program *</label>
                    <input
                      ref={simProgramRef}
                      type="file"
                      accept=".py"
                      onChange={(e) =>
                        setSimProgram(e.target.files?.[0] || null)
                      }
                      className="file-input-visible"
                    />
                    {simProgram && (
                      <span className="file-selected">{simProgram.name}</span>
                    )}
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Description *</label>
                    <input
                      ref={simDescRef}
                      type="file"
                      accept=".txt,.pdf,.docx,.doc,.html"
                      onChange={(e) =>
                        setSimDesc(e.target.files?.[0] || null)
                      }
                      className="file-input-visible"
                    />
                    {simDesc && (
                      <span className="file-selected">{simDesc.name}</span>
                    )}
                  </div>
                </div>

                <button
                  className="btn btn-primary"
                  onClick={handleSimUpload}
                  disabled={uploading || !simProgram || !simDesc || !uploadKbId}
                >
                  {uploading ? uploadProgress : "Upload Simulation Pair"}
                </button>
                <p className="hint small">
                  The .py file is stored for execution. The description is
                  optimized and embedded for RAG retrieval.
                </p>
              </div>
            </>
          )}

          {/* Detail View */}
          {view === "detail" && selectedSim && (
            <>
              <div className="card">
                <div className="card-header">
                  <h2 className="card-title">{selectedSim.name}</h2>
                  <div className="button-group">
                    <button
                      className="btn btn-small"
                      onClick={() => openEdit(selectedSim)}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() =>
                        handleDelete(selectedSim.id, selectedSim.name)
                      }
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {selectedSim.description && (
                  <p className="kb-description">{selectedSim.description}</p>
                )}
                {selectedSim.tags.length > 0 && (
                  <div className="tag-list">
                    {selectedSim.tags.map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Inputs table */}
              {selectedSim.inputs.length > 0 && (
                <div className="card">
                  <h3>Inputs</h3>
                  <div className="io-table">
                    <div className="io-header">
                      <span>Name</span>
                      <span>Description</span>
                      <span>Unit</span>
                      <span>Default</span>
                    </div>
                    {selectedSim.inputs.map((inp, idx) => (
                      <div key={idx} className="io-row readonly">
                        <span>{inp.name}</span>
                        <span>{inp.description}</span>
                        <span>{inp.unit}</span>
                        <span>{String(inp.default_value || "")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Calculations */}
              <div className="card">
                <h3>Calculations</h3>
                <pre className="prompt-preview">
                  {selectedSim.calculations}
                </pre>
              </div>

              {/* Outputs table */}
              {selectedSim.outputs.length > 0 && (
                <div className="card">
                  <h3>Outputs</h3>
                  <div className="io-table">
                    <div className="io-header">
                      <span>Name</span>
                      <span>Description</span>
                      <span>Unit</span>
                    </div>
                    {selectedSim.outputs.map((out, idx) => (
                      <div key={idx} className="io-row readonly">
                        <span>{out.name}</span>
                        <span>{out.description}</span>
                        <span>{out.unit}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Test */}
              <div className="card">
                <h3>Test Simulation</h3>
                <div className="test-inputs">
                  {selectedSim.inputs
                    .filter((i) => i.name.trim())
                    .map((input) => (
                      <div key={input.name} className="form-group">
                        <label className="form-label">
                          {input.name}
                          {input.unit && (
                            <span className="unit"> ({input.unit})</span>
                          )}
                        </label>
                        <input
                          type="text"
                          className="form-input"
                          value={testInputs[input.name] || ""}
                          onChange={(e) =>
                            setTestInputs((prev) => ({
                              ...prev,
                              [input.name]: e.target.value,
                            }))
                          }
                          placeholder={String(input.default_value || "0")}
                        />
                      </div>
                    ))}
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleTest}
                  disabled={testing}
                >
                  {testing ? "Running..." : "Run Test"}
                </button>
                {testResult && (
                  <div className="test-result">
                    <h4>Outputs</h4>
                    <div className="output-list">
                      {Object.entries(testResult.outputs).map(([key, val]) => (
                        <div key={key} className="output-item">
                          <span className="output-name">{key}</span>
                          <span className="output-value">
                            {typeof val === "number"
                              ? val.toFixed(4)
                              : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                    {Object.keys(testResult.variables || {}).length > 0 && (
                      <>
                        <h4>Intermediate Variables</h4>
                        <div className="output-list small">
                          {Object.entries(testResult.variables).map(
                            ([key, val]) => (
                              <div key={key} className="output-item">
                                <span className="output-name">{key}</span>
                                <span className="output-value">
                                  {typeof val === "number"
                                    ? val.toFixed(4)
                                    : String(val)}
                                </span>
                              </div>
                            )
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </>
          )}

          {/* Edit/Create View */}
          {view === "edit" && (
            <>
              <div className="card">
                <div className="card-header">
                  <h2 className="card-title">
                    {selectedSim ? `Edit: ${selectedSim.name}` : "New Simulation"}
                  </h2>
                  <div className="button-group">
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        if (selectedSim) {
                          openDetail(selectedSim);
                        } else {
                          setView("list");
                        }
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={handleSave}
                      disabled={saving}
                    >
                      {saving ? "Saving..." : "Save"}
                    </button>
                  </div>
                </div>

                {/* Basic info */}
                <div className="form-group">
                  <label className="form-label">Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={(e) => handleChange("name", e.target.value)}
                    placeholder="e.g., NPV Calculator"
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
                    placeholder="What does this simulation calculate?"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Tags</label>
                  <div className="tag-input-row">
                    <input
                      type="text"
                      className="form-input"
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) =>
                        e.key === "Enter" && (e.preventDefault(), addTag())
                      }
                      placeholder="Add a tag..."
                    />
                    <button
                      className="btn btn-secondary"
                      onClick={addTag}
                      type="button"
                    >
                      Add
                    </button>
                  </div>
                  <div className="tag-list">
                    {form.tags?.map((tag) => (
                      <span key={tag} className="tag removable">
                        {tag}
                        <button
                          className="tag-remove"
                          onClick={() => removeTag(tag)}
                        >
                          x
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Inputs */}
              <div className="card">
                <div className="card-header">
                  <h3>Inputs</h3>
                  <button
                    className="btn btn-small"
                    onClick={() => addIO("inputs")}
                  >
                    + Add Input
                  </button>
                </div>
                <div className="io-table">
                  <div className="io-header">
                    <span>Name</span>
                    <span>Description</span>
                    <span>Unit</span>
                    <span>Default</span>
                    <span></span>
                  </div>
                  {form.inputs.map((input, idx) => (
                    <div key={idx} className="io-row">
                      <input
                        type="text"
                        className="form-input"
                        value={input.name}
                        onChange={(e) =>
                          handleIOChange("inputs", idx, "name", e.target.value)
                        }
                        placeholder="variable_name"
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={input.description}
                        onChange={(e) =>
                          handleIOChange(
                            "inputs",
                            idx,
                            "description",
                            e.target.value
                          )
                        }
                        placeholder="Description"
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={input.unit}
                        onChange={(e) =>
                          handleIOChange("inputs", idx, "unit", e.target.value)
                        }
                        placeholder="e.g., USD"
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={input.default_value || ""}
                        onChange={(e) =>
                          handleIOChange(
                            "inputs",
                            idx,
                            "default_value",
                            e.target.value
                          )
                        }
                        placeholder="0"
                      />
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => removeIO("inputs", idx)}
                        disabled={form.inputs.length === 1}
                      >
                        x
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Calculations */}
              <div className="card">
                <h3>Calculations</h3>
                <p className="hint">
                  Python-style expressions. Use input variable names and assign
                  to output names.
                </p>
                <textarea
                  className="form-textarea code-editor"
                  value={form.calculations}
                  onChange={(e) =>
                    handleChange("calculations", e.target.value)
                  }
                  rows={12}
                  spellCheck={false}
                />
              </div>

              {/* Outputs */}
              <div className="card">
                <div className="card-header">
                  <h3>Outputs</h3>
                  <button
                    className="btn btn-small"
                    onClick={() => addIO("outputs")}
                  >
                    + Add Output
                  </button>
                </div>
                <div className="io-table">
                  <div className="io-header">
                    <span>Name</span>
                    <span>Description</span>
                    <span>Unit</span>
                    <span></span>
                  </div>
                  {form.outputs.map((output, idx) => (
                    <div key={idx} className="io-row outputs">
                      <input
                        type="text"
                        className="form-input"
                        value={output.name}
                        onChange={(e) =>
                          handleIOChange(
                            "outputs",
                            idx,
                            "name",
                            e.target.value
                          )
                        }
                        placeholder="variable_name"
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={output.description}
                        onChange={(e) =>
                          handleIOChange(
                            "outputs",
                            idx,
                            "description",
                            e.target.value
                          )
                        }
                        placeholder="Description"
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={output.unit}
                        onChange={(e) =>
                          handleIOChange(
                            "outputs",
                            idx,
                            "unit",
                            e.target.value
                          )
                        }
                        placeholder="e.g., USD"
                      />
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => removeIO("outputs", idx)}
                        disabled={form.outputs.length === 1}
                      >
                        x
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Default list view placeholder */}
          {view === "list" && !selectedSim && (
            <div className="empty-state">
              Select a simulation to view details, or upload/create a new one
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
