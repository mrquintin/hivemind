import { useEffect, useState } from "react";
import {
  listScrapedSources,
  getScrapedSource,
  createScrapedSource,
  deleteScrapedSource,
  triggerScrape,
  type ScrapedSource,
  type ScrapedSourceDetail,
} from "../api/client";

export default function ScrapedSources() {
  const [sources, setSources] = useState<ScrapedSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form
  const [urlOrQuery, setUrlOrQuery] = useState("");
  const [sourceType, setSourceType] = useState<"url" | "search_query">("url");
  const [adding, setAdding] = useState(false);

  // Detail view
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ScrapedSourceDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listScrapedSources();
      setSources(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sources");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async () => {
    const trimmed = urlOrQuery.trim();
    if (!trimmed) return;
    setAdding(true);
    setError(null);
    try {
      const created = await createScrapedSource(trimmed, sourceType);
      setSources((prev) => [created, ...prev]);
      setUrlOrQuery("");
      // Auto-trigger scraping
      try {
        await triggerScrape(created.id);
        // Refresh to get updated status
        const updated = await listScrapedSources();
        setSources(updated);
      } catch {
        // Non-critical — source was created, scrape can be retried
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add source");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteScrapedSource(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
      if (expandedId === id) {
        setExpandedId(null);
        setDetail(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete source");
    }
  };

  const handleScrape = async (id: string) => {
    setError(null);
    try {
      await triggerScrape(id);
      const updated = await listScrapedSources();
      setSources(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger scrape");
    }
  };

  const handleView = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setLoadingDetail(true);
    try {
      const data = await getScrapedSource(id);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load detail");
    } finally {
      setLoadingDetail(false);
    }
  };

  const truncate = (text: string, max: number) =>
    text.length > max ? text.slice(0, max) + "..." : text;

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const statusStyle = (status: string): React.CSSProperties => {
    const color =
      status === "completed"
        ? "#22c55e"
        : status === "failed"
          ? "#ef4444"
          : "#f59e0b";
    return { color, fontWeight: 500 };
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Web Sources</h1>
          <p className="page-subtitle">
            Manage scraped web sources for analysis context
          </p>
        </div>
      </header>

      {error && <div className="error-message">{error}</div>}

      <div className="page-content">
        {/* Add Source Form */}
        <div className="card">
          <h2 className="card-title">Add Source</h2>
          <div style={{ display: "flex", gap: "8px", alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label className="form-label">URL or Search Query</label>
              <input
                type="text"
                className="form-input"
                value={urlOrQuery}
                onChange={(e) => setUrlOrQuery(e.target.value)}
                placeholder={
                  sourceType === "url"
                    ? "https://example.com/article"
                    : "search query terms..."
                }
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
            </div>
            <div>
              <label className="form-label">Type</label>
              <select
                className="form-select"
                value={sourceType}
                onChange={(e) =>
                  setSourceType(e.target.value as "url" | "search_query")
                }
                style={{ minWidth: 140 }}
              >
                <option value="url">URL</option>
                <option value="search_query">Search Query</option>
              </select>
            </div>
            <button
              className="btn btn-primary"
              onClick={handleAdd}
              disabled={adding || !urlOrQuery.trim()}
              style={{ whiteSpace: "nowrap" }}
            >
              {adding ? "Adding..." : "Add Source"}
            </button>
          </div>
        </div>

        {/* Sources Table */}
        <div className="card">
          <h2 className="card-title">Sources</h2>
          {loading ? (
            <div className="loading">Loading...</div>
          ) : sources.length === 0 ? (
            <div className="empty-state">
              No web sources yet. Add one above to get started.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "13px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid #2a303d",
                      textAlign: "left",
                    }}
                  >
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      URL / Query
                    </th>
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      Type
                    </th>
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      Status
                    </th>
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      Error
                    </th>
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      Created
                    </th>
                    <th style={{ padding: "8px 12px", color: "#9aa4b8" }}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <>
                      <tr
                        key={source.id}
                        style={{ borderBottom: "1px solid #1e222c" }}
                      >
                        <td
                          style={{ padding: "10px 12px", maxWidth: 300 }}
                          title={source.url_or_query}
                        >
                          {truncate(source.url_or_query, 60)}
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          {source.source_type}
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={statusStyle(source.status)}>
                            {source.status}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: "10px 12px",
                            color: "#ef4444",
                            maxWidth: 200,
                          }}
                          title={source.error_message || ""}
                        >
                          {source.error_message
                            ? truncate(source.error_message, 40)
                            : "—"}
                        </td>
                        <td
                          style={{
                            padding: "10px 12px",
                            color: "#9aa4b8",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatDate(source.created_at)}
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          <div
                            style={{
                              display: "flex",
                              gap: "6px",
                              flexWrap: "nowrap",
                            }}
                          >
                            {(source.status === "pending" ||
                              source.status === "failed") && (
                              <button
                                className="btn btn-small"
                                onClick={() => handleScrape(source.id)}
                              >
                                Scrape
                              </button>
                            )}
                            {source.status === "completed" && (
                              <button
                                className="btn btn-small"
                                onClick={() => handleView(source.id)}
                              >
                                {expandedId === source.id ? "Hide" : "View"}
                              </button>
                            )}
                            <button
                              className="btn btn-small btn-danger"
                              onClick={() => handleDelete(source.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                      {expandedId === source.id && (
                        <tr key={`${source.id}-detail`}>
                          <td colSpan={6} style={{ padding: "0 12px 12px" }}>
                            {loadingDetail ? (
                              <div className="loading">Loading detail...</div>
                            ) : detail ? (
                              <div
                                style={{
                                  background: "#0d1017",
                                  border: "1px solid #2a303d",
                                  borderRadius: 8,
                                  padding: "16px",
                                  maxHeight: 300,
                                  overflowY: "auto",
                                  whiteSpace: "pre-wrap",
                                  fontSize: "12px",
                                  color: "#c8cdd6",
                                  lineHeight: 1.5,
                                }}
                              >
                                {detail.scraped_text || "(no text available)"}
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
