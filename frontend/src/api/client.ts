import type {
  Blunder,
  ChatMessage,
  DrillCard,
  IngestJob,
  OpeningStat,
  Profile,
  StyleGap,
  StyleMatch,
} from "../types";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail || message;
    } catch {
      // Keep the status-based fallback when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function ingest(username: string): Promise<IngestJob> {
  return request(`/ingest/${encodeURIComponent(username)}`, { method: "POST" });
}

export function getJob(jobId: number): Promise<IngestJob> {
  return request(`/ingest/jobs/${jobId}`);
}

export function getProfile(username: string): Promise<Profile> {
  return request(`/profile/${encodeURIComponent(username)}`);
}

export async function getStyleMatches(username: string): Promise<StyleMatch[]> {
  const result = await request<{ matches: StyleMatch[] }>(
    `/style/${encodeURIComponent(username)}/match`,
  );
  return result.matches;
}

export function getStyleGap(username: string, gm?: string): Promise<StyleGap> {
  const query = gm ? `?gm=${encodeURIComponent(gm)}` : "";
  return request(`/style-gap/${encodeURIComponent(username)}${query}`);
}

export async function getOpenings(username: string): Promise<OpeningStat[]> {
  const result = await request<{ openings: OpeningStat[] }>(
    `/openings/${encodeURIComponent(username)}`,
  );
  return result.openings;
}

export async function getBlunders(username: string): Promise<Blunder[]> {
  const result = await request<{ positions: Blunder[] }>(
    `/blunders/${encodeURIComponent(username)}?limit=12`,
  );
  return result.positions;
}

export function getDrills(username: string): Promise<DrillCard[]> {
  const path = `/drill/${encodeURIComponent(username)}/queue`;
  return request<{ created: number }>(path, { method: "POST" }).then(() => request(path));
}

export function recordDrillAttempt(
  username: string,
  cardId: number,
  attemptedMoveUci: string,
): Promise<{
  correct: boolean;
  correct_move: string | null;
  due_at: string;
  next_box: number;
}> {
  return request(`/drill/${encodeURIComponent(username)}/attempt`, {
    method: "POST",
    body: JSON.stringify({
      card_id: cardId,
      attempted_move_uci: attemptedMoveUci,
    }),
  });
}

export function askCoach(
  username: string,
  message: string,
  history: ChatMessage[],
): Promise<{ answer: string }> {
  return request("/coach", {
    method: "POST",
    body: JSON.stringify({ username, message, history }),
  });
}

export async function pollJob(
  jobId: number,
  onUpdate: (job: IngestJob) => void,
  intervalMs = 1500,
): Promise<IngestJob> {
  for (;;) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (["completed", "failed"].includes(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
}
