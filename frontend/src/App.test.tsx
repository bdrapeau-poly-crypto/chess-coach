import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("renders the username entry and demo path", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ authenticated: false, auth_required: true }), { status: 200 }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "Chess Coach" })).toBeInTheDocument();
    expect(screen.getByLabelText("Chess.com username")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try demo" })).toBeEnabled();
  });
});
