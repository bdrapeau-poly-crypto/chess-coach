from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DrillAttemptRequest(BaseModel):
    card_id: int
    attempted_move_uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$", max_length=5)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class CoachRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4_000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)


class CoachResponse(BaseModel):
    answer: str


class SessionRequest(BaseModel):
    access_key: str = Field(min_length=1, max_length=512)


class SessionResponse(BaseModel):
    authenticated: bool
    auth_required: bool
    token: str | None = None
    expires_at: datetime | None = None


class JobResponse(BaseModel):
    job_id: int
    username: str
    status: str
    deduplicated: bool


class DrillCardResponse(BaseModel):
    card_id: int
    theme: str
    box: int
    due_at: datetime
    fen: str
    label: str
    orientation: str


class StyleGapResponse(BaseModel):
    username: str
    gm_name: str
    player: dict[str, float]
    grandmaster: dict[str, float]
    gap: dict[str, float]
