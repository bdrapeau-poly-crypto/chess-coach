import { FormEvent, lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  clearPlayerSession,
  getPlayerAccount,
  hasPlayerSession,
  savePlayerWorkspace,
  authenticate,
  askCoach,
  clearSession,
  getAuthSession,
  getBlunders,
  getDrills,
  getOpenings,
  getProfile,
  getStyleGap,
  getStyleMatches,
  ingest,
  pollJob,
} from "./api/client";
import type {
  Blunder,
  ChatMessage,
  DrillCard,
  IngestJob,
  OpeningStat,
  Profile,
  AuthSession,
  StyleGap,
  StyleMatch,
} from "./types";
import "./styles.css";
import { AccountAccess } from "./components/AccountAccess";
import type { PlayerAccount } from "./api/client";

const CoachMessage = lazy(() =>
  import("./components/CoachMessage").then((module) => ({ default: module.CoachMessage })),
);
const DrillPractice = lazy(() =>
  import("./components/DrillPractice").then((module) => ({ default: module.DrillPractice })),
);
const PositionGallery = lazy(() =>
  import("./components/PositionGallery").then((module) => ({ default: module.PositionGallery })),
);
const StyleRadar = lazy(() =>
  import("./components/StyleRadar").then((module) => ({ default: module.StyleRadar })),
);
const WeaknessChart = lazy(() =>
  import("./components/WeaknessChart").then((module) => ({ default: module.WeaknessChart })),
);

type Tab = "profile" | "style" | "openings" | "blunders" | "practice" | "coach";
const LAST_PLAYER_KEY = "chess-coach-last-player";
const PENDING_JOB_KEY = "chess-coach-pending-job";

interface PendingJob {
  jobId: number;
  username: string;
}

function storedPendingJob(): PendingJob | null {
  try {
    const value = window.localStorage.getItem(PENDING_JOB_KEY);
    return value ? (JSON.parse(value) as PendingJob) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [account, setAccount] = useState<PlayerAccount | null>(null);
  const [username, setUsername] = useState("");
  const [activeUser, setActiveUser] = useState("");
  const [job, setJob] = useState<IngestJob | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [styleMatches, setStyleMatches] = useState<StyleMatch[]>([]);
  const [styleGap, setStyleGap] = useState<StyleGap | null>(null);
  const [openings, setOpenings] = useState<OpeningStat[]>([]);
  const [blunders, setBlunders] = useState<Blunder[]>([]);
  const [drills, setDrills] = useState<DrillCard[]>([]);
  const [tab, setTab] = useState<Tab>("profile");
  const [error, setError] = useState("");
  const [coachInput, setCoachInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [serviceMessage, setServiceMessage] = useState("");
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [accessKey, setAccessKey] = useState("");
  const [pendingJob, setPendingJob] = useState<PendingJob | null>(storedPendingJob);

  const beginColdStartNotice = useCallback((initial: string): () => void => {
    setServiceMessage(initial);
    const timer = globalThis.setTimeout(
      () => setServiceMessage("The free analysis service may take about a minute to wake up…"),
      3_000,
    );
    return () => {
      globalThis.clearTimeout(timer);
      setServiceMessage("");
    };
  }, []);

  const handleError = useCallback((caught: unknown, fallback: string) => {
    if (caught instanceof ApiError && caught.status === 401) {
      clearSession();
      setAuth((current) => ({
        authenticated: false,
        auth_required: current?.auth_required ?? true,
      }));
    }
    setError(caught instanceof Error ? caught.message : fallback);
  }, []);

  const loadWorkspace = useCallback(async (name: string, allowMissing = false) => {
    setBusy(true);
    setError("");
    const endNotice = beginColdStartNotice("Connecting to the analysis service…");
    let profileFound = false;
    try {
      const nextProfile = await getProfile(name);
      profileFound = true;
      const [matches, gap, openingRows, positions, cards] = await Promise.all([
        getStyleMatches(name),
        getStyleGap(name),
        getOpenings(name),
        getBlunders(name),
        getDrills(name),
      ]);
      setProfile(nextProfile);
      setStyleMatches(matches);
      setStyleGap(gap);
      setOpenings(openingRows);
      setBlunders(positions);
      setDrills(cards);
      setActiveUser(name);
      setHistory([]);
      window.localStorage.setItem(LAST_PLAYER_KEY, name);
      return true;
    } catch (caught) {
      if (!(allowMissing && !profileFound && caught instanceof ApiError && caught.status === 404)) {
        handleError(caught, "Could not load player workspace");
      }
      if (!profileFound && caught instanceof ApiError && caught.status === 404) return false;
      throw caught;
    } finally {
      endNotice();
      setBusy(false);
    }
  }, [beginColdStartNotice, handleError]);

  useEffect(() => {
    void getAuthSession()
      .then(async (session) => {
        if (!session.authenticated) clearSession();
        setAuth(session);
        let savedName = window.localStorage.getItem(LAST_PLAYER_KEY);
        if (hasPlayerSession()) {
          try {
            const saved = await getPlayerAccount();
            setAccount(saved);
            savedName = saved.workspace_username;
          } catch (caught) {
            if (caught instanceof ApiError && caught.status === 401) {
              clearPlayerSession();
              setError("Your sign-in has expired. Sign in again to restore your account.");
            } else {
              setError("Could not restore your account. Try signing in again.");
            }
          }
        }
        if (savedName && (!session.auth_required || session.authenticated)) {
          setUsername(savedName);
          await loadWorkspace(savedName).catch(() => undefined);
        }
      })
      .catch(() => {
        setAuth(null);
        setError("Could not connect to the analysis service. Reload this page to try again.");
      });
  }, [loadWorkspace]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const endNotice = beginColdStartNotice("Connecting securely…");
    try {
      const nextAuth = await authenticate(accessKey);
      setAuth(nextAuth);
      setAccessKey("");
    } catch (caught) {
      handleError(caught, "Could not verify access");
    } finally {
      endNotice();
      setBusy(false);
    }
  }

  function signOut() {
    clearSession();
    setAuth({ authenticated: false, auth_required: auth?.auth_required ?? true });
  }

  async function accountSignedIn(next: PlayerAccount) {
    setAccount(next);
    const name = next.workspace_username || activeUser;
    if (name) {
      if (!next.workspace_username) setAccount(await savePlayerWorkspace(name));
      setUsername(name);
      await loadWorkspace(name);
    }
  }

  function accountSignedOut() {
    setAccount(null);
    setProfile(null);
    setActiveUser("");
    setHistory([]);
    setUsername("");
    setJob(null);
    window.localStorage.removeItem(LAST_PLAYER_KEY);
    window.localStorage.removeItem(PENDING_JOB_KEY);
    setPendingJob(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const name = username.trim().toLowerCase();
    if (!name) return;
    try {
      if (account) setAccount(await savePlayerWorkspace(name));
      if (await loadWorkspace(name, true)) return;
      await analyzeNewest(name);
    } catch (caught) {
      handleError(caught, "Could not open player workspace");
    }
  }

  async function analyzeNewest(name: string) {
    if (!name) return;
    if (auth?.auth_required && !auth.authenticated) {
      setError("Enter the private beta access key before analyzing games.");
      return;
    }
    setBusy(true);
    setError("");
    const endNotice = beginColdStartNotice("Starting the analysis service…");
    try {
      const created = await ingest(name);
      setJob(created);
      const nextPending = { jobId: created.job_id, username: name };
      window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify(nextPending));
      setPendingJob(nextPending);
      const finished = await pollJob(created.job_id, setJob);
      if (finished.status === "failed") throw new Error(finished.error || "Ingest failed");
      window.localStorage.removeItem(PENDING_JOB_KEY);
      setPendingJob(null);
      await loadWorkspace(name);
    } catch (caught) {
      handleError(caught, "Ingest failed");
    } finally {
      endNotice();
      setBusy(false);
    }
  }

  async function resumeAnalysis() {
    if (!pendingJob) return;
    if (auth?.auth_required && !auth.authenticated) {
      setError("Enter the private beta access key before resuming analysis.");
      return;
    }
    setBusy(true);
    setError("");
    const endNotice = beginColdStartNotice("Resuming the saved analysis job…");
    try {
      const finished = await pollJob(pendingJob.jobId, setJob);
      if (finished.status === "failed") throw new Error(finished.error || "Ingest failed");
      window.localStorage.removeItem(PENDING_JOB_KEY);
      const completedUsername = pendingJob.username;
      setPendingJob(null);
      await loadWorkspace(completedUsername);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        window.localStorage.removeItem(PENDING_JOB_KEY);
        setPendingJob(null);
      }
      handleError(caught, "Could not resume analysis");
    } finally {
      endNotice();
      setBusy(false);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const question = coachInput.trim();
    if (!question || !activeUser) return;
    if (auth?.auth_required && !auth.authenticated) {
      setError("Enter the private beta access key before using the AI coach.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await askCoach(activeUser, question, history);
      setHistory((current) => [
        ...current,
        { role: "user", content: question },
        { role: "assistant", content: response.answer },
      ]);
      setCoachInput("");
    } catch (caught) {
      handleError(caught, "Coach request failed");
    } finally {
      setBusy(false);
    }
  }

  async function refreshDrills() {
    setDrills(await getDrills(activeUser));
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Your games. Your patterns. Your next move.</p>
        <h1>Chess Coach</h1>
        <p className="lede">
          Stockfish-backed analysis turns your own recurring mistakes into a focused practice plan.
        </p>
        <form className="player-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="username">Chess.com username</label>
          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Chess.com username"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={25}
          />
          <button
            disabled={busy || !auth || Boolean(auth.auth_required && !auth.authenticated)}
            type="submit"
          >
            Open my analysis
          </button>
        </form>
        <p className="player-note">
          Enter a Chess.com username to analyze public games. No password or Chess.com sign-in is needed.
          Existing analysis opens immediately. A first visit starts analysis of your recent games.
          Practice feedback stays in this session; it does not verify ownership of the Chess.com account.
        </p>
        <AccountAccess account={account} onSignedIn={accountSignedIn} onSignedOut={accountSignedOut} />
        {auth?.auth_required && (
          auth.authenticated ? (
            <div className="auth-status">
              <span>Private beta access active</span>
              <button className="text-button" type="button" onClick={signOut}>Sign out</button>
            </div>
          ) : (
            <form className="auth-form" onSubmit={signIn}>
              <label htmlFor="access-key">Private beta access key</label>
              <input
                id="access-key"
                type="password"
                value={accessKey}
                onChange={(event) => setAccessKey(event.target.value)}
                autoComplete="current-password"
              />
              <button disabled={busy || !accessKey} type="submit">Unlock</button>
            </form>
          )
        )}
        {pendingJob && (
          <button
            className="resume-button"
            disabled={busy || !auth || Boolean(auth.auth_required && !auth.authenticated)}
            type="button"
            onClick={() => void resumeAnalysis()}
          >
            Resume analysis for {pendingJob.username}
          </button>
        )}
        {serviceMessage && <p className="status" role="status">{serviceMessage}</p>}
        {job && (
          <p className="status">
            {job.status === "queued" ? "Waiting for analysis" : job.status === "running" ? "Analyzing your games" : job.status === "completed" ? "Analysis complete" : "Analysis stopped"}
            {" · "}{job.games_analyzed ?? 0} games newly analyzed
            {job.games_fetched ? ` of ${job.games_fetched} fetched` : ""}
            {job.status === "completed" && !job.games_analyzed && !job.games_failed && " · No new games needed analysis"}
            {Boolean(job.games_failed) && ` · ${job.games_failed} could not be analyzed`}
          </p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </header>

      {profile && (
        <section className="dashboard">
          <div className="section-heading">
            <p className="eyebrow">Player workspace</p>
            <h2>{profile.username}</h2>
            <p>Your saved workspace contains {profile.summary.games} games. Updates check your 50 most recent games, keep completed analysis, and add new results.</p>
            <button type="button" disabled={busy || !auth || Boolean(auth.auth_required && !auth.authenticated)} onClick={() => void analyzeNewest(activeUser)}>
              Analyze my newest games
            </button>
          </div>
          <nav className="tabs" aria-label="Player analysis">
            {(["profile", "style", "openings", "blunders", "practice", "coach"] as Tab[]).map(
              (name) => (
                <button
                  type="button"
                  className={tab === name ? "active" : ""}
                  aria-current={tab === name ? "page" : undefined}
                  onClick={() => setTab(name)}
                  key={name}
                >
                  {name}
                </button>
              ),
            )}
          </nav>

          <Suspense fallback={<article className="panel">Loading view…</article>}>
            {tab === "profile" && (
              <>
                <div className="stats">
                  <article><strong>{profile.summary.games}</strong><span>games</span></article>
                  <article><strong>{profile.summary.wins}</strong><span>wins</span></article>
                  <article>
                    <strong>{profile.summary.local_accuracy ?? "—"}</strong>
                    <span>local accuracy</span>
                  </article>
                </div>
                <article className="panel chart-panel">
                  <p className="eyebrow">Weakness fingerprint</p>
                  {profile.weaknesses.length ? (
                    <WeaknessChart weaknesses={profile.weaknesses} />
                  ) : (
                    <p>No analyzed weaknesses yet. Demo reference data does not fabricate games.</p>
                  )}
                </article>
              </>
            )}

            {tab === "style" && (
              <article className="panel split-panel">
                <div>
                  <p className="eyebrow">Closest illustrative reference</p>
                  <h3>{styleMatches[0]?.gm_name ?? "No match available"}</h3>
                  <p>
                    {styleMatches[0]
                      ? `${styleMatches[0].similarity}% vector similarity`
                      : "Analyze games to calculate a style vector."}
                  </p>
                  <small>
                    Compared with five illustrative seeded grandmaster references—not an
                    all-grandmaster corpus or a statistically validated playing-style model.
                  </small>
                </div>
                <div className="radar">{styleGap && <StyleRadar gap={styleGap} />}</div>
              </article>
            )}

            {tab === "openings" && (
              <article className="panel table-wrap">
                <table>
                  <thead><tr><th>Opening</th><th>Games</th><th>W–L–D</th><th>Local accuracy</th></tr></thead>
                  <tbody>
                    {openings.map((opening) => (
                      <tr key={opening.opening}>
                        <td>{opening.opening}</td>
                        <td>{opening.games}</td>
                        <td>{opening.wins}–{opening.losses}–{opening.draws}</td>
                        <td>{opening.local_accuracy ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!openings.length && <p>No analyzed openings yet.</p>}
              </article>
            )}

            {tab === "blunders" && (
              <article className="panel"><PositionGallery positions={blunders} /></article>
            )}

            {tab === "practice" && (
              <article className="panel">
                <DrillPractice
                  username={activeUser}
                  cards={drills}
                  onComplete={() => void refreshDrills()}
                />
              </article>
            )}

            {tab === "coach" && (
              <article className="panel coach-panel">
                <p className="eyebrow">Ask your coach</p>
                <div className="conversation" aria-live="polite">
                  {history.map((message, index) => (
                    <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
                      {message.role === "assistant" ? (
                        <CoachMessage>{message.content}</CoachMessage>
                      ) : (
                        <p>{message.content}</p>
                      )}
                    </div>
                  ))}
                </div>
                <form onSubmit={ask}>
                  <textarea
                    value={coachInput}
                    onChange={(event) => setCoachInput(event.target.value)}
                    placeholder="What should I work on next?"
                    rows={3}
                  />
                  <button
                    disabled={busy || !auth || Boolean(auth.auth_required && !auth.authenticated)}
                    type="submit"
                  >
                    Ask coach
                  </button>
                </form>
              </article>
            )}
          </Suspense>
        </section>
      )}
    </main>
  );
}
