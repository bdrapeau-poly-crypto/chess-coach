import { Chessboard } from "react-chessboard";
import type { Blunder } from "../types";

export function PositionGallery({ positions }: { positions: Blunder[] }) {
  if (!positions.length) return <p>No analyzed blunder positions yet.</p>;
  return (
    <div className="position-grid">
      {positions.slice(0, 4).map((position) => (
        <article className="position-card" key={position.id}>
          <Chessboard
            id={`blunder-${position.id}`}
            position={position.fen}
            arePiecesDraggable={false}
          />
          <h3>{position.theme.replaceAll("_", " ")}</h3>
          <p>
            Played <code>{position.played_move}</code>
            {position.best_move ? <> · Better <code>{position.best_move}</code></> : null}
          </p>
          <small>{position.centipawn_loss} centipawns lost</small>
        </article>
      ))}
    </div>
  );
}
