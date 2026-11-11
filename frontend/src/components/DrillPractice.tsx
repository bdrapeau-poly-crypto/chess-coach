import { useEffect, useState } from "react";
import { Chess } from "chess.js";
import { Chessboard } from "react-chessboard";
import type { Arrow, Piece, Square } from "react-chessboard/dist/chessboard/types";
import { recordDrillAttempt } from "../api/client";
import { moveNotation } from "../utils/moveNotation";
import type { DrillCard } from "../types";

type DrillPhase =
  | "idle"
  | "grading"
  | "correct"
  | "incorrect"
  | "reviewing"
  | "review-correct"
  | "review-incorrect";

function hintForTheme(theme: string): string {
  const label = theme.replaceAll("_", " ");
  return `Look for checks, captures, and forcing threats connected to ${label}.`;
}

function promotionForMove(source: string, target: string, piece: Piece): string | undefined {
  const reachesBackRank =
    (source[1] === "7" && target[1] === "8") ||
    (source[1] === "2" && target[1] === "1");
  if (!reachesBackRank) return undefined;
  return piece[1].toLowerCase() === "p" ? "q" : piece[1].toLowerCase();
}

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
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<DrillPhase>("idle");
  const [boardFen, setBoardFen] = useState("");
  const [correctMove, setCorrectMove] = useState<string | null>(null);
  const [showHint, setShowHint] = useState(false);
  const [completedCardIds, setCompletedCardIds] = useState<Set<number>>(() => new Set());
  const card = cards.find((candidate) => !completedCardIds.has(candidate.card_id));

  useEffect(() => {
    setCompletedCardIds(new Set());
  }, [username]);

  useEffect(() => {
    setBoardFen(card?.fen ?? "");
    setFeedback("");
    setError("");
    setPhase("idle");
    setCorrectMove(null);
    setShowHint(false);
  }, [card?.card_id, card?.fen]);

  if (!cards.length) return <p>No drills are queued yet. Ask the coach to queue practice.</p>;
  if (!card) return <p className="feedback">Session complete — every queued position was reviewed.</p>;

  const activeCard = card;
  const playerColor = activeCard.orientation === "white" ? "w" : "b";
  const positionTurn = new Chess(activeCard.fen).turn();
  const canMove = phase === "idle" || phase === "reviewing";
  const answerArrow: Arrow[] =
    phase === "incorrect" && correctMove
      ? [[correctMove.slice(0, 2) as Square, correctMove.slice(2, 4) as Square, "#d46445"]]
      : [];

  function resetForReview() {
    setBoardFen(activeCard.fen);
    setFeedback("Try the position again. Review attempts do not change the schedule.");
    setError("");
    setPhase("reviewing");
  }

  function nextPosition() {
    setCompletedCardIds((current) => new Set(current).add(activeCard.card_id));
    onComplete();
  }

  function onPieceDrop(source: Square, target: Square, piece: Piece): boolean {
    if (!canMove || piece[0] !== playerColor || positionTurn !== playerColor) return false;

    const game = new Chess(activeCard.fen);
    try {
      const move = game.move({
        from: source,
        to: target,
        promotion: promotionForMove(source, target, piece),
      });
      const attempted = `${move.from}${move.to}${move.promotion ?? ""}`.toLowerCase();
      setBoardFen(game.fen());
      setError("");

      if (phase === "reviewing") {
        const isCorrect = attempted === correctMove?.toLowerCase();
        setPhase(isCorrect ? "review-correct" : "review-incorrect");
        setFeedback(
          isCorrect
            ? "That’s the move. Continue when you’re ready."
            : "That is legal, but it is not the saved best move. Reset and try again.",
        );
        return true;
      }

      setPhase("grading");
      setFeedback("Checking your move…");
      void recordDrillAttempt(username, activeCard.card_id, attempted)
        .then((result) => {
          setCorrectMove(result.correct_move);
          setPhase(result.correct ? "correct" : "incorrect");
          setFeedback(
            result.progress_saved === false
              ? (result.correct ? "Correct. Continue to the next position." : "Not quite. Review the best move, then try again.")
              : (result.correct ? "Correct. This card will return later." : "Not quite. This card returns to box one."),
          );
        })
        .catch((caught: unknown) => {
          setBoardFen(activeCard.fen);
          setPhase("idle");
          setFeedback("");
          setError(caught instanceof Error ? caught.message : "Could not grade this move");
        });
      return true;
    } catch {
      setError("That move is not legal in this position.");
      return false;
    }
  }

  return (
    <div className="drill-layout">
      <div className="drill-board">
        <Chessboard
          id={`drill-${activeCard.card_id}`}
          position={boardFen || activeCard.fen}
          boardOrientation={activeCard.orientation}
          arePiecesDraggable={canMove && positionTurn === playerColor}
          isDraggablePiece={({ piece }) =>
            canMove && positionTurn === playerColor && piece[0] === playerColor
          }
          onPieceDrop={onPieceDrop}
          promotionDialogVariant="modal"
          customArrows={answerArrow}
        />
      </div>
      <div>
        <p className="eyebrow">
          Box {activeCard.box} · {activeCard.theme.replaceAll("_", " ")}
        </p>
        <h3>{activeCard.label}</h3>
        <p>Move the piece on the board. The position comes from one of your games.</p>
        <p className="drill-progress">
          {completedCardIds.size + 1} of {cards.length} queued
        </p>
        {showHint && <p className="drill-hint">{hintForTheme(activeCard.theme)}</p>}
        {feedback && (
          <p className={`feedback ${phase.includes("incorrect") ? "incorrect" : ""}`} aria-live="polite">
            {feedback}
          </p>
        )}
        {phase === "incorrect" && correctMove && (
          <p className="answer">Best move: <strong>{moveNotation(activeCard.fen, correctMove)}</strong></p>
        )}
        {error && <p className="error drill-error" role="alert">{error}</p>}
        <div className="drill-actions">
          {!showHint && phase === "idle" && (
            <button className="secondary dark" type="button" onClick={() => setShowHint(true)}>
              Show hint
            </button>
          )}
          {(phase === "incorrect" || phase === "review-incorrect") && (
            <button className="secondary dark" type="button" onClick={resetForReview}>
              Try again
            </button>
          )}
          {(phase === "correct" || phase === "incorrect" || phase.startsWith("review-")) && (
            <button type="button" onClick={nextPosition}>
              {completedCardIds.size + 1 === cards.length ? "Finish session" : "Next position"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
