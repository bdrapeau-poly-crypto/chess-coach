import { Chess } from "chess.js";

export function moveNotation(fen: string, uci: string | null): string {
  if (!uci) return "Unavailable";
  try {
    return new Chess(fen).move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }).san;
  } catch {
    return "Move unavailable";
  }
}

export function readableMoveReferences(text: string, fens: string[] = []): string {
  return text.replace(/\b([a-h][1-8])([a-h][1-8])([qrbn])?\b/g, (raw, from: string, to: string, promotion?: string) => {
    const options = new Set(fens.map(fen => moveNotation(fen, raw)).filter(san => san !== "Move unavailable"));
    if (options.size === 1) return [...options][0];
    const pieces: Record<string, string> = { q: "queen", r: "rook", b: "bishop", n: "knight" };
    return `${from} to ${to}${promotion ? `, promote to ${pieces[promotion]}` : ""}`;
  });
}

export function readableCoachMarkdown(markdown: string): string {
  const fens: string[] = [];
  for (const match of markdown.matchAll(/```chess-board\s*([\s\S]*?)```/g)) {
    try { const value = JSON.parse(match[1]); if (typeof value.fen === "string") fens.push(value.fen); }
    catch { /* Invalid board blocks are handled by the board renderer. */ }
  }
  return markdown.split(/(```[\s\S]*?```)/g)
    .map(part => part.startsWith("```") ? part : readableMoveReferences(part, fens)).join("");
}
