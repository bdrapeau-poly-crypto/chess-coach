from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import EngineCache


class StockfishUnavailable(RuntimeError):
    pass


COMMON_STOCKFISH_PATHS = (
    "/opt/homebrew/bin/stockfish",
    "/opt/homebrew/opt/stockfish/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/games/stockfish",
)


def resolve_stockfish_path(configured_path: str | None = None) -> str | None:
    candidates = [configured_path, shutil.which("stockfish"), *COMMON_STOCKFISH_PATHS]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate).stat().st_mode & 0o111:
            return str(Path(candidate).resolve())
    return None


@dataclass(frozen=True)
class Evaluation:
    score_cp: int
    best_move: chess.Move | None
    cached: bool


class StockfishAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = resolve_stockfish_path(settings.stockfish_path)
        if not self.path:
            raise StockfishUnavailable("No executable Stockfish binary was found")
        self.engine: chess.engine.SimpleEngine | None = None
        self.signature = f"stockfish:{Path(self.path).name}:depth={settings.stockfish_depth}"

    def __enter__(self) -> StockfishAnalyzer:
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self.engine.configure({"Hash": self.settings.stockfish_hash_mb, "Threads": 1})
        try:
            name = self.engine.id.get("name", "Stockfish")
            self.signature = f"{name}:depth={self.settings.stockfish_depth}"
        except Exception:
            pass
        return self

    def __exit__(self, *_: object) -> None:
        if self.engine:
            self.engine.quit()
            self.engine = None

    def _key(self, fen: str, perspective: chess.Color) -> str:
        material = f"{fen}|{self.signature}|{int(perspective)}"
        return hashlib.sha256(material.encode()).hexdigest()

    def evaluate(
        self, session: Session, board: chess.Board, perspective: chess.Color
    ) -> Evaluation:
        key = self._key(board.fen(), perspective)
        cached = session.scalar(select(EngineCache).where(EngineCache.cache_key == key))
        if cached:
            return Evaluation(
                cached.score_cp,
                chess.Move.from_uci(cached.best_move_uci) if cached.best_move_uci else None,
                True,
            )
        if not self.engine:
            raise RuntimeError("StockfishAnalyzer must be used as a context manager")
        info = self.engine.analyse(
            board,
            chess.engine.Limit(depth=self.settings.stockfish_depth),
        )
        score = info["score"].pov(perspective).score(mate_score=100_000)
        if score is None:
            score = 0
        pv = info.get("pv") or []
        best_move = pv[0] if pv else None
        session.add(
            EngineCache(
                cache_key=key,
                fen=board.fen(),
                engine_signature=self.signature,
                depth=self.settings.stockfish_depth,
                score_cp=score,
                best_move_uci=best_move.uci() if best_move else None,
            )
        )
        session.flush()
        return Evaluation(score, best_move, False)


def stockfish_health(settings: Settings) -> dict:
    path = resolve_stockfish_path(settings.stockfish_path)
    if not path:
        return {"status": "unavailable", "engine": None, "probe": False}
    try:
        with chess.engine.SimpleEngine.popen_uci(path, timeout=5) as engine:
            info = engine.analyse(chess.Board(), chess.engine.Limit(depth=1))
            return {
                "status": "ok",
                "engine": engine.id.get("name", "Stockfish"),
                "probe": "score" in info,
            }
    except Exception as exc:
        return {
            "status": "error",
            "engine": "Stockfish",
            "probe": False,
            "detail": type(exc).__name__,
        }
