import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => { cleanup(); window.localStorage.clear(); vi.restoreAllMocks(); });

describe("App", () => {
  it("renders the username entry without a demo path", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ authenticated: false, auth_required: true }), { status: 200 }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "Chess Coach" })).toBeInTheDocument();
    expect(screen.getByLabelText("Chess.com username")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try demo" })).not.toBeInTheDocument();
  });
  it("enables public analysis without showing a password field", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ authenticated: true, auth_required: false }), { status: 200 }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open my analysis" })).toBeEnabled());
    expect(screen.queryByLabelText("Private beta access key")).not.toBeInTheDocument();
    expect(screen.getByText(/No password or Chess.com sign-in is needed/)).toBeInTheDocument();
  });
});


function workspaceFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    let data: unknown = {};
    if (path.endsWith("/auth/session")) data = { authenticated: true, auth_required: false };
    else if (path.endsWith("/account/me")) data = { login_name: "brian", workspace_username: "player" };
    else if (path.includes("/profile/")) data = { username: "player", summary: { games: 20, wins: 10, losses: 8, draws: 2, local_accuracy: 80 }, weaknesses: [] };
    else if (path.includes("/match")) data = { matches: [] };
    else if (path.includes("/openings/")) data = { openings: [] };
    else if (path.includes("/blunders/")) data = { positions: [] };
    else if (path.includes("/drill/")) data = [];
    else if (path.endsWith("/ingest/player")) data = { job_id: 1, username: "player", status: "queued" };
    else if (path.includes("/ingest/jobs/")) data = { job_id: 1, username: "player", status: "completed", games_analyzed: 0, games_fetched: 20 };
    return new Response(JSON.stringify(data), { status: 200 });
  });
}

it("restores an account workspace without starting analysis", async () => {
  window.localStorage.setItem("chess-coach-player-session", "test-session");
  const fetchMock = workspaceFetch();
  render(<App />);
  expect(await screen.findByRole("heading", { name: "player" })).toBeInTheDocument();
  expect(screen.getByText("brian")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/ingest/"))).toBe(false);
});

it("opens existing analysis and starts an update only when explicitly requested", async () => {
  const fetchMock = workspaceFetch();
  render(<App />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Open my analysis" })).toBeEnabled());
  fireEvent.change(screen.getByLabelText("Chess.com username"), { target: { value: "player" } });
  fireEvent.click(screen.getByRole("button", { name: "Open my analysis" }));
  await screen.findByRole("heading", { name: "player" });
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/ingest/"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Analyze my newest games" }));
  await screen.findByText(/No new games needed analysis/);
  expect(fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith("/ingest/player") && init?.method === "POST")).toHaveLength(1);
});

it("remembers a guest workspace without requiring an account", async () => {
  window.localStorage.setItem("chess-coach-last-player", "player");
  const fetchMock = workspaceFetch();
  render(<App />);
  await screen.findByRole("heading", { name: "player" });
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/ingest/"))).toBe(false);
});
