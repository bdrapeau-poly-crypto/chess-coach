from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime

import chess.pgn


class PgnParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedGame:
    game: chess.pgn.Game
    pgn: str
    pgn_hash: str
    external_id: str
    played_at: datetime | None
    user_color: str
    result: str
    opponent: str | None
    time_control: str | None
    eco: str | None
    opening_name: str | None


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not normalized or len(normalized) > 64:
        raise ValueError("Username must contain 1 to 64 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if any(char not in allowed for char in normalized):
        raise ValueError("Username contains unsupported characters")
    return normalized


def parse_game(payload: dict, username: str) -> ParsedGame:
    pgn = str(payload.get("pgn") or "").strip()
    if not pgn:
        raise PgnParseError("Game did not contain PGN")
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise PgnParseError("PGN could not be parsed")
    if game.errors:
        raise PgnParseError(f"PGN contained parser errors: {game.errors[0]}")

    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")
    normalized = normalize_username(username)
    if white.lower() == normalized:
        color, opponent = "white", black or None
    elif black.lower() == normalized:
        color, opponent = "black", white or None
    else:
        raise PgnParseError(f"PGN does not contain requested user {username}")

    pgn_hash = hashlib.sha256(pgn.encode("utf-8")).hexdigest()
    url = str(payload.get("url") or headers.get("Link") or "")
    external_id = str(payload.get("uuid") or url.rsplit("/", 1)[-1] or pgn_hash)
    end_time = payload.get("end_time")
    played_at = datetime.fromtimestamp(int(end_time), UTC) if end_time else None

    result_token = headers.get("Result", "*")
    if result_token == "1/2-1/2":
        result = "draw"
    elif (result_token == "1-0" and color == "white") or (
        result_token == "0-1" and color == "black"
    ):
        result = "win"
    elif result_token in {"1-0", "0-1"}:
        result = "loss"
    else:
        result = "unknown"

    return ParsedGame(
        game=game,
        pgn=pgn,
        pgn_hash=pgn_hash,
        external_id=external_id[:128],
        played_at=played_at,
        user_color=color,
        result=result,
        opponent=opponent,
        time_control=str(payload.get("time_control") or headers.get("TimeControl") or "") or None,
        eco=headers.get("ECO"),
        opening_name=headers.get("Opening") or headers.get("Variation"),
    )
