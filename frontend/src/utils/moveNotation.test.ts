import { describe, expect, it } from "vitest";
import { Chess } from "chess.js";
import { moveNotation, readableCoachMarkdown, readableMoveReferences } from "./moveNotation";

describe("displayed move notation", () => {
  it("formats pawns, pieces, captures, castling, and promotions using the position", () => {
    expect(moveNotation(new Chess().fen(), "e2e4")).toBe("e4");
    expect(moveNotation(new Chess().fen(), "g1f3")).toBe("Nf3");
    expect(moveNotation("4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1", "c3d5")).toBe("Nxd5");
    expect(moveNotation("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1")).toBe("O-O");
    expect(moveNotation("8/P7/8/8/8/8/4K3/7k w - - 0 1", "a7a8n")).toBe("a8=N");
  });
  it("does not invent notation for an illegal move or invalid position", () => {
    expect(moveNotation(new Chess().fen(), "c3d5")).toBe("Move unavailable");
    expect(moveNotation("invalid", "e2e4")).toBe("Move unavailable");
    expect(readableMoveReferences("Try c3d5")).toBe("Try c3 to d5");
  });
  it("uses grounded board positions in coach prose while preserving board JSON", () => {
    const block = '```chess-board\n' + JSON.stringify({ fen: new Chess().fen(), label: "Try e2e4", orientation: "white" }) + '\n```';
    expect(readableCoachMarkdown("Try e2e4.\n" + block)).toBe("Try e4.\n" + block);
    expect(readableMoveReferences("Try e2e4", [new Chess().fen()])).toBe("Try e4");
  });
});
