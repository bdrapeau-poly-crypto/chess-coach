import { useState } from "react";
import { Chessboard } from "react-chessboard";
import { recordDrillAttempt } from "../api/client";
import type { DrillCard } from "../types";

export function DrillPractice({
  username,
  cards,
  onComplete,
}: {
  username: string;
  cards: DrillCard[];
  onComplete: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const card = cards[0];
  if (!card) return <p>No drills are queued yet. Ask the coach to queue practice.</p>;

  function onPieceDrop(source: string, target: string): boolean {
    const attempted = `${source}${target}`.toLowerCase();
    void recordDrillAttempt(username, card.card_id, attempted).then((result) => {
      setFeedback(
        result.correct
          ? "Correct — this card will return later."
          : "Not quite — back to box one.",
      );
      window.setTimeout(onComplete, 650);
    });
    return true;
  }

  return (
    <div className="drill-layout">
      <div className="drill-board">
        <Chessboard
          id={`drill-${card.card_id}`}
          position={card.fen}
          boardOrientation={card.orientation}
          onPieceDrop={onPieceDrop}
        />
      </div>
      <div>
        <p className="eyebrow">Box {card.box} · {card.theme.replaceAll("_", " ")}</p>
        <h3>{card.label}</h3>
        <p>Move the piece on the board. The position comes from one of your games.</p>
        {feedback && <p className="feedback">{feedback}</p>}
      </div>
    </div>
  );
}
