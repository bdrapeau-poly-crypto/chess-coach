import { Chessboard } from "react-chessboard";
import ReactMarkdown from "react-markdown";
import { parseBoardBlock } from "../utils/chessBoard";

export function CoachMessage({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        code({ className, children: codeChildren }) {
          if (className === "language-chess-board") {
            const board = parseBoardBlock(String(codeChildren).trim());
            if (!board) return <p className="error">The coach returned an invalid board.</p>;
            return (
              <figure className="coach-board">
                <Chessboard
                  id={`coach-${board.fen}`}
                  position={board.fen}
                  boardOrientation={board.orientation}
                  arePiecesDraggable={false}
                />
                <figcaption>{board.label}</figcaption>
              </figure>
            );
          }
          return <code className={className}>{codeChildren}</code>;
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
