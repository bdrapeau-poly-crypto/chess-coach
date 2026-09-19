from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import BlunderPosition, Game, WeaknessProfile
from app.practice.leitner import queue_from_blunders
from app.profiling.profiles import get_user

TOOL_DEFINITIONS = [
    {
        "name": "get_recent_games",
        "description": "Get the player's most recent analyzed games and summary metrics.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_weakness_profile",
        "description": "Get aggregated tactical weaknesses, frequency, and average severity.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_game_details",
        "description": "Get one owned game and its blunder positions, including FENs.",
        "input_schema": {
            "type": "object",
            "properties": {"game_id": {"type": "integer", "minimum": 1}},
            "required": ["game_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_opening_stats",
        "description": "Get the player's opening results and local accuracy metric.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
            "additionalProperties": False,
        },
    },
    {
        "name": "queue_practice",
        "description": "Idempotently queue drills from the player's own blundered positions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "minimum_severity": {"type": "integer", "minimum": 100, "maximum": 2000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class CoachTools:
    def __init__(self, session: Session, username: str) -> None:
        self.session = session
        self.user = get_user(session, username)
        if self.user is None:
            raise ValueError(f"Unknown player: {username}")

    def execute(self, name: str, arguments: dict) -> dict | list:
        handlers = {
            "get_recent_games": self.get_recent_games,
            "get_weakness_profile": self.get_weakness_profile,
            "get_game_details": self.get_game_details,
            "get_opening_stats": self.get_opening_stats,
            "queue_practice": self.queue_practice,
        }
        if name not in handlers:
            raise ValueError(f"Unknown coach tool: {name}")
        return handlers[name](**arguments)

    def get_recent_games(self, limit: int = 5) -> list[dict]:
        games = self.session.scalars(
            select(Game)
            .where(Game.user_id == self.user.id)
            .order_by(Game.played_at.desc(), Game.id.desc())
            .limit(min(limit, 10))
        ).all()
        return [
            {
                "id": game.id,
                "played_at": game.played_at.isoformat() if game.played_at else None,
                "opponent": game.opponent,
                "color": game.user_color,
                "result": game.result,
                "opening": game.opening_name,
                "local_accuracy": game.accuracy,
                "average_centipawn_loss": game.average_centipawn_loss,
                "analysis_status": game.analysis_status,
            }
            for game in games
        ]

    def get_weakness_profile(self) -> list[dict]:
        rows = self.session.scalars(
            select(WeaknessProfile)
            .where(WeaknessProfile.user_id == self.user.id)
            .order_by(WeaknessProfile.frequency.desc())
        ).all()
        return [
            {
                "theme": row.motif,
                "frequency": row.frequency,
                "average_severity": row.average_severity,
            }
            for row in rows
        ]

    def get_game_details(self, game_id: int) -> dict:
        game = self.session.scalar(
            select(Game).where(Game.id == game_id, Game.user_id == self.user.id)
        )
        if game is None:
            return {"error": "Game not found for this player"}
        positions = self.session.scalars(
            select(BlunderPosition)
            .where(BlunderPosition.game_id == game.id)
            .order_by(BlunderPosition.ply)
            .limit(30)
        ).all()
        return {
            "id": game.id,
            "opponent": game.opponent,
            "result": game.result,
            "opening": game.opening_name,
            "positions": [
                {
                    "ply": item.ply,
                    "fen": item.fen_before,
                    "played_move": item.played_move_uci,
                    "best_move": item.best_move_uci,
                    "centipawn_loss": item.centipawn_loss,
                    "theme": item.motif,
                }
                for item in positions
            ],
        }

    def get_opening_stats(self, limit: int = 10) -> list[dict]:
        opening = func.coalesce(Game.opening_name, Game.eco, "Unknown")
        rows = self.session.execute(
            select(
                opening.label("opening"),
                func.count(Game.id),
                func.sum(case((Game.result == "win", 1), else_=0)),
                func.sum(case((Game.result == "loss", 1), else_=0)),
                func.sum(case((Game.result == "draw", 1), else_=0)),
                func.avg(Game.accuracy),
            )
            .where(Game.user_id == self.user.id)
            .group_by(opening)
            .order_by(func.count(Game.id).desc())
            .limit(min(limit, 20))
        ).all()
        return [
            {
                "opening": name,
                "games": int(games),
                "wins": int(wins or 0),
                "losses": int(losses or 0),
                "draws": int(draws or 0),
                "local_accuracy": round(float(accuracy), 1) if accuracy is not None else None,
            }
            for name, games, wins, losses, draws, accuracy in rows
        ]

    def queue_practice(self, minimum_severity: int = 100, limit: int = 10) -> dict:
        created = queue_from_blunders(
            self.session,
            self.user.id,
            minimum_severity=minimum_severity,
            limit=min(limit, 20),
        )
        self.session.commit()
        return {"created": created, "queued_at": datetime.now(UTC).isoformat()}
