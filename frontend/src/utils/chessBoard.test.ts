import { describe, expect, it } from "vitest";
import { parseBoardBlock } from "./chessBoard";

const valid = {
  fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  label: "Find the best move",
  orientation: "white",
};

describe("parseBoardBlock", () => {
  it("accepts a valid board", () => expect(parseBoardBlock(JSON.stringify(valid))).toEqual(valid));
  it("accepts black orientation", () => {
    expect(parseBoardBlock(JSON.stringify({ ...valid, orientation: "black" }))?.orientation).toBe("black");
  });
  it("rejects malformed JSON", () => expect(parseBoardBlock("{")) .toBeNull());
  it("rejects an incomplete FEN", () => {
    expect(parseBoardBlock(JSON.stringify({ ...valid, fen: "8/8/8/8/8/8/8/8" }))).toBeNull();
  });
  it("rejects empty labels", () => {
    expect(parseBoardBlock(JSON.stringify({ ...valid, label: "" }))).toBeNull();
  });
});
