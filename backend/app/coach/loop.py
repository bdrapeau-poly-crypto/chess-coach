from __future__ import annotations

import json

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.coach.tools import TOOL_DEFINITIONS, CoachTools
from app.config import Settings

SYSTEM_PROMPT = """You are a precise, encouraging chess coach. Ground every player-specific
claim in tool results. Call tools when live player data is needed. Never invent games,
positions, ratings, engine scores, or grandmaster comparisons. The field local_accuracy is
this application's transparent centipawn-loss-derived metric, not Chess.com Accuracy.

When a position would help, emit exactly this fenced format with valid JSON:
```chess-board
{"fen":"<FEN>","label":"<short instruction>","orientation":"white|black"}
```
Only use FENs returned by tools. Keep the response concise and actionable.
"""


class CoachUnavailable(RuntimeError):
    pass


def _serialize_content(content: list) -> list[dict]:
    result: list[dict] = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
    return result


def run_coach_loop(
    session: Session,
    settings: Settings,
    *,
    username: str,
    message: str,
    history: list[dict],
) -> str:
    if not settings.anthropic_api_key:
        raise CoachUnavailable("ANTHROPIC_API_KEY is not configured")
    tools = CoachTools(session, username)
    client = Anthropic(api_key=settings.anthropic_api_key)
    messages = history[-settings.coach_history_limit :] + [{"role": "user", "content": message}]

    for _ in range(settings.coach_max_tool_rounds):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1200,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        serialized = _serialize_content(response.content)
        messages.append({"role": "assistant", "content": serialized})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            return "\n".join(block.text for block in response.content if block.type == "text")
        results = []
        for call in calls:
            try:
                value = tools.execute(call.name, dict(call.input))
                content = json.dumps(value, default=str)
                is_error = False
            except Exception as exc:
                content = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                is_error = True
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    raise RuntimeError("Coach exceeded the maximum number of tool rounds")
