import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

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
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze my games" })).toBeEnabled());
    expect(screen.queryByLabelText("Private beta access key")).not.toBeInTheDocument();
    expect(screen.getByText(/No password or Chess.com sign-in is needed/)).toBeInTheDocument();
  });
});
