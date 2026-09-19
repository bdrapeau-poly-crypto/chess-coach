import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  askCoach,
  getBlunders,
  getDrills,
  getOpenings,
  getProfile,
  getStyleGap,
  ingest,
  recordDrillAttempt,
  request,
} from "./client";

afterEach(() => vi.restoreAllMocks());

describe("request", () => {
  it("returns parsed JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(request("/health")).resolves.toEqual({ status: "ok" });
  });

  it("surfaces API detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(request("/missing")).rejects.toEqual(new ApiError("Not found", 404));
  });

  it("uses a status fallback for non-JSON errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("bad gateway", { status: 502 }));
    await expect(request("/broken")).rejects.toEqual(new ApiError("Request failed (502)", 502));
  });

  it("encodes usernames for ingestion", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ job_id: 1, username: "a b", status: "queued" }), {
        status: 202,
      }),
    );
    await ingest("a b");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/ingest/a%20b"), expect.objectContaining({ method: "POST" }));
  });

  it("encodes profile usernames", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ username: "a/b", summary: {}, weaknesses: [] }), { status: 200 }),
    );
    await getProfile("a/b");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/profile/a%2Fb"), expect.anything());
  });

  it("encodes a selected grandmaster", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ username: "u", gm_name: "Mikhail Tal" }), { status: 200 }),
    );
    await getStyleGap("u", "Mikhail Tal");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("gm=Mikhail%20Tal"), expect.anything());
  });

  it("sends attempted moves without trusting client correctness", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ correct: true, next_box: 2, due_at: "later" }), { status: 200 }),
    );
    await recordDrillAttempt("player", 7, "e2e4");
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(options.body))).toEqual({ card_id: 7, attempted_move_uci: "e2e4" });
  });

  it("sends bounded coach history", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ answer: "Train forks." }), { status: 200 }),
    );
    await askCoach("player", "What next?", [{ role: "assistant", content: "Review complete." }]);
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(options.body)).history).toHaveLength(1);
  });

  it("extracts opening rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ openings: [{ opening: "Sicilian", games: 3 }] }), { status: 200 }),
    );
    await expect(getOpenings("player")).resolves.toEqual([{ opening: "Sicilian", games: 3 }]);
  });

  it("extracts blunder positions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ positions: [{ id: 4, theme: "fork" }] }), { status: 200 }),
    );
    await expect(getBlunders("player")).resolves.toEqual([{ id: 4, theme: "fork" }]);
  });

  it("returns drill queue payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([{ card_id: 2, theme: "pin" }]), { status: 200 }),
    );
    await expect(getDrills("player")).resolves.toEqual([{ card_id: 2, theme: "pin" }]);
  });
});
