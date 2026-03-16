import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  DATA_FILES,
  FEASIBILITY_FIRST_RUN,
  FEASIBILITY_SECOND_RUN,
  INITIAL_AGGREGATE_CONCLUSIONS,
  OUTPUT_DOCUMENT,
  PRACTICALITY_UNITS,
  REVISED_AGGREGATE_CONCLUSIONS,
  SCENARIO,
  THEORY_UNITS,
} from "./demoData";

const VALID_KEY = "remove_this_key_later";

/** Explanatory text for each phase/step, simplified from the product description. */
function getExplanation(
  phase: Phase,
  analysisStep: AnalysisStep,
  runNumber: number
): string {
  if (phase === "login" || phase === "login_fade_out") {
    return "Enter your access key to connect to the Hivemind client.";
  }
  if (phase === "main") {
    return "Enter your problem in the text box. Set sufficiency (how many distinct conclusions you want), feasibility threshold (1–100), and theory network density (the token size of each unit’s knowledge base). Click Submit to start analysis.";
  }
  if (phase !== "analysis") return "";

  switch (analysisStep) {
    case "theory_analyzing":
      return runNumber === 1
        ? "Theory network units each hold a portion of the strategic knowledge base (sized by your theory network density). They are generating initial solutions using your data and their knowledge, then will share and critique each other’s solutions."
        : "The theory network is generating a new set of solutions from scratch after the veto.";
    case "monitor_initial":
      return "The monitor is aggregating similar solutions from the theory network and counting distinct conclusions. When the count reaches your sufficiency value, the debate stops and the monitor will pass the aggregated solutions to the practicality network.";
    case "monitor_revision":
      return "Units are revising their solutions based on critiques from other units. The monitor keeps combining similar solutions and counting until the number of distinct conclusions is at or below your sufficiency value.";
    case "pass_to_practicality":
      return "The monitor is passing the aggregated solutions (without theoretical justifications) to the practicality network. Each solution will be rated for feasibility by each practicality unit.";
    case "practicality_voting":
      return "Each practicality network unit (e.g. legal, PR, financial) rates the current solution from 1–100. If the average score is at or below your feasibility threshold, the whole list is vetoed and the theory network must start over.";
    case "veto":
      return "The average feasibility score was at or below your feasibility threshold. The full list of solutions is vetoed; the theory network will generate a new set of solutions from scratch.";
    case "restart":
      return "Restarting the theory network to produce a new list of solutions after the veto.";
    case "practicality_verify":
      return "All solutions passed the feasibility threshold. The monitor is finalizing the output for you.";
    case "done":
      return "Analysis complete. The final solutions have passed both the theory network debate and the practicality network’s feasibility checks.";
    default:
      return "";
  }
}

// Slider ranges per product description
const SUFFICIENCY_MIN = 1;
const SUFFICIENCY_MAX = 10;
const FEASIBILITY_MIN = 1;
const FEASIBILITY_MAX = 100;
const DENSITY_MIN = 500;
const DENSITY_MAX = 50000;

type Phase =
  | "login"
  | "login_fade_out"
  | "main"
  | "analysis"
  | "output";

type AnalysisStep =
  | "theory_analyzing"
  | "monitor_initial"
  | "monitor_revision"
  | "pass_to_practicality"
  | "practicality_voting"
  | "veto"
  | "restart"
  | "practicality_verify"
  | "done";

function LoginScreen({
  userKey,
  onKeyChange,
  onSubmit,
  error,
  isLoading,
}: {
  userKey: string;
  onKeyChange: (v: string) => void;
  onSubmit: () => void;
  error: string;
  isLoading: boolean;
}) {
  return (
    <div className="login-screen">
      <div className="login-content">
        <h1 className="login-title">HIVEMIND</h1>
        <p className="login-subtitle">Strategic Analysis Terminal</p>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          <label className="login-label">
            User key
          </label>
          <input
            type="text"
            className="login-input"
            value={userKey}
            onChange={(e) => onKeyChange(e.target.value)}
            placeholder="Enter access key"
            autoFocus
          />
          {error && <div className="login-error">{error}</div>}
          <button type="submit" className="login-button" disabled={isLoading}>
            {isLoading ? "Verifying…" : "Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}

function LoginFadeOut({
  onDone,
  userKey,
}: {
  onDone: () => void;
  userKey: string;
}) {
  const [overlayActive, setOverlayActive] = useState(false);
  useEffect(() => {
    const start = requestAnimationFrame(() => {
      requestAnimationFrame(() => setOverlayActive(true));
    });
    return () => cancelAnimationFrame(start);
  }, []);
  useEffect(() => {
    const t = setTimeout(onDone, 2200);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <div className="login-fade-out">
      <div className="login-screen">
        <div className="login-content">
          <h1 className="login-title">HIVEMIND</h1>
          <p className="login-subtitle">Strategic Analysis Terminal</p>
          <p className="login-label">User key</p>
          <p className="login-key-mask">{userKey ? "••••••••" : "—"}</p>
        </div>
      </div>
      <div className={`login-fade-overlay ${overlayActive ? "active" : ""}`} aria-hidden />
    </div>
  );
}

function SliderWithInput({
  label,
  value,
  min,
  max,
  step,
  onChange,
  leftLabel,
  rightLabel,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  leftLabel: string;
  rightLabel: string;
  disabled?: boolean;
}) {
  return (
    <div className="slider-block">
      <div className="slider-top">
        <span className="slider-label">{label}</span>
        <input
          type="number"
          className="slider-number"
          min={min}
          max={max}
          step={step ?? 1}
          value={value}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v)));
          }}
          disabled={disabled}
        />
      </div>
      <input
        type="range"
        className="slider-range"
        min={min}
        max={max}
        step={step ?? 1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
      />
      <div className="slider-extremes">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
    </div>
  );
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("login");
  const [userKey, setUserKey] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  const [problemText, setProblemText] = useState(SCENARIO.decisionContext);
  const [sufficiency, setSufficiency] = useState(2);
  const [feasibility, setFeasibility] = useState(60);
  const [density, setDensity] = useState(8000);
  const [promptLocked, setPromptLocked] = useState(false);
  const [dataPanelOpen, setDataPanelOpen] = useState(false);
  const [openFile, setOpenFile] = useState<typeof DATA_FILES[0] | null>(null);

  const [analysisStep, setAnalysisStep] = useState<AnalysisStep>("theory_analyzing");
  const [runNumber, setRunNumber] = useState(1);
  const [monitorConclusions, setMonitorConclusions] = useState<string[]>([]);
  const [monitorCount, setMonitorCount] = useState(0);
  const [revisionUsed, setRevisionUsed] = useState(false);
  const [votingSolutionIndex, setVotingSolutionIndex] = useState(0);
  const [votingUnitIndex, setVotingUnitIndex] = useState(-1);
  const [showVeto, setShowVeto] = useState(false);
  const [conclusionsDrifting, setConclusionsDrifting] = useState(false);
  const [showOutputModal, setShowOutputModal] = useState(false);
  const [analysisPaused, setAnalysisPaused] = useState(false);

  const handleLogin = useCallback(() => {
    const key = userKey.trim();
    if (!key) {
      setLoginError("Enter a user key.");
      return;
    }
    setLoginLoading(true);
    setLoginError("");
    setTimeout(() => {
      if (key === VALID_KEY) {
        setPhase("login_fade_out");
      } else {
        setLoginError("Invalid key.");
      }
      setLoginLoading(false);
    }, 400);
  }, [userKey]);

  const handleMatrixDone = useCallback(() => setPhase("main"), []);

  const startAnalysis = useCallback(() => {
    setPromptLocked(true);
    setPhase("analysis");
    setAnalysisStep("theory_analyzing");
    setRunNumber(1);
    setMonitorConclusions([]);
    setMonitorCount(0);
    setRevisionUsed(false);
    setVotingSolutionIndex(0);
    setVotingUnitIndex(-1);
    setShowVeto(false);
    setConclusionsDrifting(false);
    setAnalysisPaused(false);
  }, []);

  const feasibilityRef = useRef(feasibility);
  feasibilityRef.current = feasibility;

  // Scripted analysis timeline: single effect drives all step transitions (paused = no advances)
  useEffect(() => {
    if (phase !== "analysis" || analysisPaused) return;

    const scores =
      runNumber === 1 ? FEASIBILITY_FIRST_RUN : FEASIBILITY_SECOND_RUN;
    const numUnits = PRACTICALITY_UNITS.length;
    const numSolutions = REVISED_AGGREGATE_CONCLUSIONS.length;
    const threshold = feasibilityRef.current;

    let cancelled = false;
    const schedule = (ms: number, fn: () => void) => {
      const t = setTimeout(() => {
        if (!cancelled) fn();
      }, ms);
      return () => clearTimeout(t);
    };

    const timers: ReturnType<typeof setTimeout>[] = [];

    if (analysisStep === "theory_analyzing" && runNumber === 1) {
      timers.push(
        schedule(5500, () => {
          setMonitorConclusions(INITIAL_AGGREGATE_CONCLUSIONS);
          setMonitorCount(INITIAL_AGGREGATE_CONCLUSIONS.length);
          setAnalysisStep("monitor_initial");
        })
      );
    }

    if (analysisStep === "monitor_initial" && !revisionUsed) {
      timers.push(
        schedule(6000, () => {
          setRevisionUsed(true);
          setMonitorConclusions([]);
          setMonitorCount(0);
          setAnalysisStep("monitor_revision");
        })
      );
    }

    if (analysisStep === "monitor_revision") {
      timers.push(
        schedule(3500, () => {
          setMonitorConclusions(REVISED_AGGREGATE_CONCLUSIONS);
          setMonitorCount(REVISED_AGGREGATE_CONCLUSIONS.length);
          setAnalysisStep("pass_to_practicality");
          setConclusionsDrifting(true);
        })
      );
    }

    if (analysisStep === "pass_to_practicality") {
      timers.push(
        schedule(5500, () => {
          setConclusionsDrifting(false);
          setAnalysisStep("practicality_voting");
          setVotingSolutionIndex(0);
          setVotingUnitIndex(0);
        })
      );
    }

    // Advance voting: one timeout per "tick" (next unit or next solution/veto/done)
    if (
      analysisStep === "practicality_voting" &&
      votingUnitIndex >= 0 &&
      votingUnitIndex < numUnits
    ) {
      timers.push(
        schedule(1300, () => {
          if (votingUnitIndex < numUnits - 1) {
            setVotingUnitIndex((i) => i + 1);
          } else {
            const solScores = scores[votingSolutionIndex] ?? [];
            const avg =
              solScores.reduce((a, b) => a + b, 0) / numUnits;
            const veto = avg <= threshold;
            setVotingUnitIndex(-1);
            if (veto && runNumber === 1) {
              setAnalysisStep("veto");
              setShowVeto(true);
            } else if (votingSolutionIndex < numSolutions - 1) {
              setVotingSolutionIndex((i) => i + 1);
              setVotingUnitIndex(0);
            } else if (runNumber === 2) {
              setAnalysisStep("practicality_verify");
            } else {
              setAnalysisStep("veto");
              setShowVeto(true);
            }
          }
        })
      );
    }

    if (analysisStep === "veto" && showVeto) {
      timers.push(
        schedule(4500, () => {
          setShowVeto(false);
          setAnalysisStep("restart");
          setMonitorConclusions([]);
          setMonitorCount(0);
        })
      );
    }

    if (analysisStep === "restart") {
      timers.push(
        schedule(2800, () => {
          setRunNumber(2);
          setAnalysisStep("theory_analyzing");
        })
      );
    }

    if (analysisStep === "theory_analyzing" && runNumber === 2) {
      timers.push(
        schedule(5000, () => {
          setMonitorConclusions(REVISED_AGGREGATE_CONCLUSIONS);
          setMonitorCount(REVISED_AGGREGATE_CONCLUSIONS.length);
          setAnalysisStep("pass_to_practicality");
          setConclusionsDrifting(true);
        })
      );
    }

    if (analysisStep === "practicality_verify") {
      timers.push(schedule(2500, () => setAnalysisStep("done")));
    }

    if (analysisStep === "done") {
      timers.push(
        schedule(1000, () => setShowOutputModal(true))
      );
    }

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [
    phase,
    analysisStep,
    runNumber,
    revisionUsed,
    votingSolutionIndex,
    votingUnitIndex,
    showVeto,
    analysisPaused,
  ]);

  const votingScores =
    runNumber === 1 ? FEASIBILITY_FIRST_RUN : FEASIBILITY_SECOND_RUN;
  const numUnits = PRACTICALITY_UNITS.length;
  const numSolutions = REVISED_AGGREGATE_CONCLUSIONS.length;

  const explanation = getExplanation(phase, analysisStep, runNumber);

  if (phase === "login") {
    return (
      <>
        <LoginScreen
          userKey={userKey}
          onKeyChange={setUserKey}
          onSubmit={handleLogin}
          error={loginError}
          isLoading={loginLoading}
        />
        <div className="explanation-bar" role="status">{explanation}</div>
      </>
    );
  }

  if (phase === "login_fade_out") {
    return (
      <>
        <LoginFadeOut userKey={userKey} onDone={handleMatrixDone} />
        <div className="explanation-bar" role="status">{explanation}</div>
      </>
    );
  }

  if (phase === "main") {
    return (
      <>
      <div className={`app-main main-fade-in ${dataPanelOpen ? "data-open" : ""}`}>
        <div className="main-content">
          <header className="main-header">
            <span className="main-brand">HIVEMIND</span>
            <span className="main-badge">CLIENT DEMO</span>
          </header>

          <form
            className="input-section"
            onSubmit={(e) => {
              e.preventDefault();
              if (!promptLocked && problemText.trim()) startAnalysis();
            }}
          >
            <div className="input-block">
              <label className="input-label">Problem description</label>
              <textarea
                className="problem-input"
                value={problemText}
                onChange={(e) => setProblemText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !promptLocked && problemText.trim()) {
                    e.preventDefault();
                    startAnalysis();
                  }
                }}
                placeholder="Describe your strategic problem..."
                rows={5}
                readOnly={promptLocked}
              />
              {promptLocked && (
                <div className="input-locked">Prompt locked — analysis in progress</div>
              )}
            </div>

            <SliderWithInput
              label="Sufficiency"
              value={sufficiency}
              min={SUFFICIENCY_MIN}
              max={SUFFICIENCY_MAX}
              onChange={setSufficiency}
              leftLabel="Fewer conclusions (1)"
              rightLabel="More conclusions (10)"
              disabled={promptLocked}
            />
            <SliderWithInput
              label="Feasibility threshold"
              value={feasibility}
              min={FEASIBILITY_MIN}
              max={FEASIBILITY_MAX}
              onChange={setFeasibility}
              leftLabel="Stricter (1)"
              rightLabel="Lenient (100)"
              disabled={promptLocked}
            />
            <SliderWithInput
              label="Theory network density"
              value={density}
              min={DENSITY_MIN}
              max={DENSITY_MAX}
              step={500}
              onChange={setDensity}
              leftLabel="Min token size"
              rightLabel="Full knowledge base"
              disabled={promptLocked}
            />

            <div className="actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDataPanelOpen(true)}
              >
                Access data
              </button>
              {!promptLocked && (
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!problemText.trim()}
                >
                  Submit
                </button>
              )}
            </div>
          </form>
        </div>

        {dataPanelOpen && (
          <div className="data-panel">
            <div className="data-panel-header">
              <span className="data-panel-title">Client data</span>
              <button
                type="button"
                className="data-panel-close"
                onClick={() => {
                  setDataPanelOpen(false);
                  setOpenFile(null);
                }}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="data-panel-files">
              {DATA_FILES.map((f) => (
                <button
                  key={f.name}
                  type="button"
                  className={`data-file ${openFile?.name === f.name ? "open" : ""}`}
                  onClick={() => setOpenFile(openFile?.name === f.name ? null : f)}
                >
                  {f.name}
                </button>
              ))}
            </div>
            {openFile && (
              <div className="data-file-content">
                <pre>{openFile.content}</pre>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="explanation-bar" role="status">{explanation}</div>
      </>
    );
  }

  if (phase === "analysis") {
    const isTheoryActive =
      analysisStep === "theory_analyzing" ||
      (analysisStep === "restart" && runNumber === 2);

    return (
      <>
      <div className="app-analysis">
        <header className="main-header analysis-header">
          <span className="main-brand">HIVEMIND</span>
          <span className="main-badge">Analysis</span>
          <button
            type="button"
            className={`btn btn-pause ${analysisPaused ? "paused" : ""}`}
            onClick={() => setAnalysisPaused((p) => !p)}
            aria-label={analysisPaused ? "Resume" : "Pause"}
          >
            {analysisPaused ? "Resume" : "Pause"}
          </button>
        </header>

        <div className="analysis-grid">
          <section className={`panel theory-panel ${isTheoryActive ? "active" : ""}`}>
            <h3 className="panel-title">Theory network</h3>
            <ul className="unit-list">
              {THEORY_UNITS.map((name) => (
                <li key={name} className="unit-item">
                  {name}
                </li>
              ))}
            </ul>
          </section>

          <section className="panel monitor-panel">
            <h3 className="panel-title">
              Monitor
              {monitorCount > 0 && (
                <span className="monitor-count">Conclusions: {monitorCount}</span>
              )}
            </h3>
            <div className="monitor-box">
              {revisionUsed && analysisStep === "monitor_revision" && (
                <div className="monitor-revision-label">Revision applied</div>
              )}
              {monitorConclusions.map((c, i) => (
                <div key={i} className="monitor-conclusion">
                  {c}
                </div>
              ))}
              {conclusionsDrifting && (
                <div className="monitor-drifting" aria-hidden>
                  Passing to practicality network…
                </div>
              )}
            </div>
          </section>

          <section className="panel practicality-panel">
            <h3 className="panel-title">Practicality network</h3>
            <ul className="unit-list">
              {PRACTICALITY_UNITS.map((name, i) => (
                <li
                  key={name}
                  className={`unit-item ${
                    analysisStep === "practicality_voting" &&
                    votingUnitIndex === i
                      ? "voting"
                      : ""
                  }`}
                >
                  {name}
                  {analysisStep === "practicality_voting" &&
                    votingUnitIndex === i &&
                    votingScores[votingSolutionIndex]?.[i] != null && (
                      <span className="feasibility-score">
                        {votingScores[votingSolutionIndex][i]}/100
                      </span>
                    )}
                </li>
              ))}
            </ul>
            {analysisStep === "practicality_voting" && (
              <div className="voting-label">
                Evaluating solution {votingSolutionIndex + 1} of {numSolutions}
              </div>
            )}
          </section>
        </div>

        {conclusionsDrifting && (
          <div className="drift-orbit" aria-hidden>
            {REVISED_AGGREGATE_CONCLUSIONS.slice(0, 3).map((c, i) => (
              <div key={i} className="drift-chip">
                {c.slice(0, 60)}…
              </div>
            ))}
          </div>
        )}

        {showVeto && (
          <div className="veto-overlay">
            <div className="veto-box">VETO</div>
            <p className="veto-caption">Feasibility below threshold — restarting analysis</p>
          </div>
        )}

        {showOutputModal && (
          <div className="output-overlay" onClick={() => setShowOutputModal(false)}>
            <div
              className="output-modal"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="output-header">
                <h2>Analysis complete</h2>
                <button
                  type="button"
                  className="output-close"
                  onClick={() => setShowOutputModal(false)}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>
              <div className="output-body">
                <pre className="output-text">{OUTPUT_DOCUMENT}</pre>
              </div>
              <div className="output-footer">
                <button
                  type="button"
                  className="btn btn-download"
                  onClick={() => {}}
                  aria-label="Download as TXT (cosmetic)"
                >
                  Download as TXT
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="explanation-bar" role="status">{explanation}</div>
      </>
    );
  }

  return null;
}
