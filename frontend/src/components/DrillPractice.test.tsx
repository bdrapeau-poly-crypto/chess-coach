import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DrillCard } from "../types";
import { DrillPractice } from "./DrillPractice";

const mocks = vi.hoisted(() => ({
  boardProps: {} as Record<string, unknown>,
  recordAttempt: vi.fn(),
}));

vi.mock("react-chessboard", () => ({
  Chessboard: (props: Record<string, unknown>) => {
    mocks.boardProps = props;
    return <div data-testid="chessboard" />;
  },
}));

vi.mock("../api/client", () => ({
  recordDrillAttempt: mocks.recordAttempt,
}));

const card: DrillCard = {
  card_id: 7,
  theme: "fork",
  box: 2,
  due_at: "2026-09-19T00:00:00Z",
  fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  label: "Find the improvement",
  orientation: "white",
};

function drop(source: string, target: string, piece = "wP") {
  const onPieceDrop = mocks.boardProps.onPieceDrop as (
    from: string,
    to: string,
    movedPiece: string,
  ) => boolean;
  return onPieceDrop(source, target, piece);
}

describe("DrillPractice", () => {
  afterEach(cleanup);

  beforeEach(() => {
    mocks.recordAttempt.mockReset();
    mocks.boardProps = {};
  });

  it("permits only the player's pieces and rejects illegal moves", async () => {
    render(<DrillPractice username="player" cards={[card]} onComplete={vi.fn()} />);
    const canDrag = mocks.boardProps.isDraggablePiece as (args: {
      piece: string;
      sourceSquare: string;
    }) => boolean;
    expect(canDrag({ piece: "wP", sourceSquare: "e2" })).toBe(true);
    expect(canDrag({ piece: "bP", sourceSquare: "e7" })).toBe(false);
    expect(drop("e2", "e5")).toBe(false);
    expect(mocks.recordAttempt).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("not legal");
  });

  it("submits a legal move once and locks while grading", async () => {
    let resolveAttempt!: (value: unknown) => void;
    mocks.recordAttempt.mockReturnValue(new Promise((resolve) => { resolveAttempt = resolve; }));
    render(<DrillPractice username="player" cards={[card]} onComplete={vi.fn()} />);

    act(() => expect(drop("e2", "e4")).toBe(true));
    expect(mocks.recordAttempt).toHaveBeenCalledWith("player", 7, "e2e4");
    expect(mocks.boardProps.arePiecesDraggable).toBe(false);

    await act(async () => {
      resolveAttempt({ correct: true, correct_move: "e2e4", next_box: 3, due_at: "later" });
    });
    expect(await screen.findByText(/Correct/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish session" })).toBeEnabled();
  });

  it("reveals the answer and supports an ungraded retry", async () => {
    mocks.recordAttempt.mockResolvedValue({
      correct: false,
      correct_move: "e2e4",
      next_box: 1,
      due_at: "later",
    });
    render(<DrillPractice username="player" cards={[card]} onComplete={vi.fn()} />);

    act(() => expect(drop("g1", "f3", "wN")).toBe(true));
    expect(await screen.findByText(/Best move:/)).toHaveTextContent("e4");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    act(() => expect(drop("e2", "e4")).toBe(true));

    expect(await screen.findByText(/That’s the move/)).toBeInTheDocument();
    expect(mocks.recordAttempt).toHaveBeenCalledTimes(1);
  });

  it("includes the selected promotion piece in UCI notation", async () => {
    const promotionCard = {
      ...card,
      fen: "8/P7/8/8/8/8/4K3/7k w - - 0 1",
    };
    mocks.recordAttempt.mockResolvedValue({
      correct: true,
      correct_move: "a7a8n",
      next_box: 3,
      due_at: "later",
    });
    render(<DrillPractice username="player" cards={[promotionCard]} onComplete={vi.fn()} />);

    act(() => expect(drop("a7", "a8", "wN")).toBe(true));
    await waitFor(() =>
      expect(mocks.recordAttempt).toHaveBeenCalledWith("player", 7, "a7a8n"),
    );
  });

  it("restores the position and unlocks after a grading error", async () => {
    mocks.recordAttempt.mockRejectedValue(new Error("Backend unavailable"));
    render(<DrillPractice username="player" cards={[card]} onComplete={vi.fn()} />);

    act(() => expect(drop("e2", "e4")).toBe(true));
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
    expect(mocks.boardProps.position).toBe(card.fen);
    expect(mocks.boardProps.arePiecesDraggable).toBe(true);
  });

  it("shows a theme hint and queued-card progress", () => {
    render(<DrillPractice username="player" cards={[card, { ...card, card_id: 8 }]} onComplete={vi.fn()} />);
    expect(screen.getByText("1 of 2 queued")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show hint" }));
    expect(screen.getByText(/forcing threats connected to fork/)).toBeInTheDocument();
  });

  it("finishes without immediately re-showing a rescheduled single card", async () => {
    const onComplete = vi.fn();
    mocks.recordAttempt.mockResolvedValue({
      correct: true,
      correct_move: "e2e4",
      next_box: 3,
      due_at: "later",
    });
    render(<DrillPractice username="player" cards={[card]} onComplete={onComplete} />);

    act(() => expect(drop("e2", "e4")).toBe(true));
    fireEvent.click(await screen.findByRole("button", { name: "Finish session" }));

    expect(onComplete).toHaveBeenCalledOnce();
    expect(screen.getByText(/Session complete/)).toBeInTheDocument();
  });
});
