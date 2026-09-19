import { FormEvent, lazy, Suspense, useState } from "react";
import {
  askCoach,
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
  StyleGap,
  StyleMatch,
} from "./types";
import "./styles.css";

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

export default function App() {
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

  async function loadWorkspace(name: string) {
    setBusy(true);
    setError("");
    try {
      const [nextProfile, matches, gap, openingRows, positions, cards] = await Promise.all([
        getProfile(name),
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
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load player workspace");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const name = username.trim().toLowerCase();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const created = await ingest(name);
      setJob(created);
      const finished = await pollJob(created.job_id, setJob);
      if (finished.status === "failed") throw new Error(finished.error || "Ingest failed");
      await loadWorkspace(name);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ingest failed");
    } finally {
      setBusy(false);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const question = coachInput.trim();
    if (!question || !activeUser) return;
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
      setError(caught instanceof Error ? caught.message : "Coach request failed");
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
          />
          <button disabled={busy} type="submit">Analyze my games</button>
          <button
            disabled={busy}
            type="button"
            className="secondary"
            onClick={() => void loadWorkspace("demo")}
          >
            Try demo
          </button>
        </form>
        {job && (
          <p className="status">
            Job {job.job_id}: {job.status} · {job.games_analyzed ?? 0} analyzed
          </p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </header>

      {profile && (
        <section className="dashboard">
          <div className="section-heading">
            <p className="eyebrow">Player workspace</p>
            <h2>{profile.username}</h2>
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
                  <p className="eyebrow">Closest reference</p>
                  <h3>{styleMatches[0]?.gm_name ?? "No match available"}</h3>
                  <p>
                    {styleMatches[0]
                      ? `${styleMatches[0].similarity}% vector similarity`
                      : "Analyze games to calculate a style vector."}
                  </p>
                  <small>Current seed profiles are illustrative, not an all-GM corpus.</small>
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
                  <button disabled={busy} type="submit">Ask coach</button>
                </form>
              </article>
            )}
          </Suspense>
        </section>
      )}
    </main>
  );
}
