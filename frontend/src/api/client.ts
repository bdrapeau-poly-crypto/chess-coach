import type {
  Blunder,
  AuthSession,
  ChatMessage,
  DrillCard,
  IngestJob,
  OpeningStat,
  Profile,
  StyleGap,
  StyleMatch,
} from "../types";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export interface PlayerAccount {
  login_name: string;
  workspace_username: string | null;
  recovery_codes?: string[];
}

const PLAYER_SESSION_KEY = "chess-coach-player-session";
export function hasPlayerSession(): boolean {
  return Boolean(window.localStorage.getItem(PLAYER_SESSION_KEY));
}
export function clearPlayerSession(): void {
  window.localStorage.removeItem(PLAYER_SESSION_KEY);
}
export function getPlayerAccount(): Promise<PlayerAccount> {
  return request("/account/me");
}
export async function playerSignIn(
  mode: "login" | "register", loginName: string, password: string,
): Promise<PlayerAccount> {
  const account = await request<PlayerAccount & { token: string }>(`/account/${mode}`, {
    method: "POST", body: JSON.stringify({ login_name: loginName, password }),
  });
  window.localStorage.setItem(PLAYER_SESSION_KEY, account.token);
  return account;
}
export async function playerSignOut(): Promise<void> {
  try {
    await request("/account/logout", { method: "POST" });
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error;
  }
  clearPlayerSession();
}
export function savePlayerWorkspace(username: string): Promise<PlayerAccount> {
  return request("/account/workspace", { method: "POST", body: JSON.stringify({ username }) });
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

const SESSION_KEY = "chess-coach-session";
let sessionToken = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(SESSION_KEY);

export function setSessionToken(token: string | null): void {
  sessionToken = token;
  if (typeof sessionStorage === "undefined") return;
  if (token) sessionStorage.setItem(SESSION_KEY, token);
  else sessionStorage.removeItem(SESSION_KEY);
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  retries?: number;
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 90_000, retries, ...fetchInit } = init;
  const method = (fetchInit.method || "GET").toUpperCase();
  const retryCount = retries ?? (method === "GET" ? 1 : 0);
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${API_URL}${path}`, {
        ...fetchInit,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(typeof localStorage !== "undefined" && localStorage.getItem(PLAYER_SESSION_KEY)
            ? { "X-Player-Session": localStorage.getItem(PLAYER_SESSION_KEY)! } : {}),
          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
          ...fetchInit.headers,
        },
      });
      if (!response.ok) {
        if ([502, 503, 504].includes(response.status) && attempt < retryCount) {
          await wait(1_500 * (attempt + 1));
          continue;
        }
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
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (attempt < retryCount) {
        await wait(1_500 * (attempt + 1));
        continue;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(
          "The analysis service is taking longer than expected. Try again in a moment.",
          0,
        );
      }
      throw new ApiError("Could not reach the analysis service", 0);
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }
  throw new ApiError("Could not reach the analysis service", 0);
}

export function getAuthSession(): Promise<AuthSession> {
  return request("/auth/session", { timeoutMs: 90_000 });
}

export async function authenticate(accessKey: string): Promise<AuthSession> {
  const result = await request<AuthSession>("/auth/session", {
    method: "POST",
    body: JSON.stringify({ access_key: accessKey }),
  });
  if (result.token) setSessionToken(result.token);
  return result;
}

export function clearSession(): void {
  setSessionToken(null);
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
  return request(path);
}

export function recordDrillAttempt(
  username: string,
  cardId: number,
  attemptedMoveUci: string,
): Promise<{
  correct: boolean;
  progress_saved?: boolean;
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
  maxDurationMs = 30 * 60 * 1000,
): Promise<IngestJob> {
  const startedAt = Date.now();
  for (;;) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (["completed", "failed"].includes(job.status)) return job;
    if (Date.now() - startedAt >= maxDurationMs) {
      throw new ApiError("Analysis is still running. You can safely return and resume it later.", 0);
    }
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
}


export function generateRecoveryCodes(password: string): Promise<{ recovery_codes: string[] }> {
  return request("/account/recovery-codes", { method: "POST", body: JSON.stringify({ password }) });
}
export async function resetPlayerPassword(loginName: string, recoveryCode: string, password: string): Promise<{ recovery_codes: string[] }> {
  const result = await request<{ recovery_codes: string[] }>("/account/reset-password", {
    method: "POST", body: JSON.stringify({ login_name: loginName, recovery_code: recoveryCode, password }),
  });
  clearPlayerSession();
  return result;
}
