export interface BoardBlock {
  fen: string;
  label: string;
  orientation: "white" | "black";
}

export function parseBoardBlock(value: string): BoardBlock | null {
  try {
    const parsed = JSON.parse(value) as Partial<BoardBlock>;
    if (
      typeof parsed.fen === "string" &&
      parsed.fen.trim().split(/\s+/).length === 6 &&
      typeof parsed.label === "string" &&
      parsed.label.trim().length > 0 &&
      (parsed.orientation === "white" || parsed.orientation === "black")
    ) {
      return parsed as BoardBlock;
    }
  } catch {
    return null;
  }
  return null;
}
