import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the username entry and demo path", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Chess Coach" })).toBeInTheDocument();
    expect(screen.getByLabelText("Chess.com username")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try demo" })).toBeEnabled();
  });
});
