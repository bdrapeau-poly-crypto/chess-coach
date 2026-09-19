from __future__ import annotations

import json
from dataclasses import dataclass

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)
from openai import OpenAI
from sqlalchemy.orm import Session

from app.coach.budget import (
    AiBudgetExceeded,
    anthropic_actual_cost,
    estimate_anthropic_call_cost,
    reconcile_anthropic_call,
    reserve_anthropic_call,
)
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


@dataclass(frozen=True)
class CoachRunResult:
    answer: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_rounds: int = 0
    cost_usd: float = 0.0


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


def _openai_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        }
        for tool in TOOL_DEFINITIONS
    ]


def _run_openai_loop(
    tools: CoachTools,
    settings: Settings,
    *,
    message: str,
    history: list[dict],
) -> CoachRunResult:
    if not settings.openai_api_key:
        raise CoachUnavailable("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=settings.openai_api_key)
    input_items: list = history[-settings.coach_history_limit :] + [
        {"role": "user", "content": message}
    ]
    tool_definitions = _openai_tools()
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0

    for round_index in range(settings.coach_max_tool_rounds):
        response = client.responses.create(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            instructions=SYSTEM_PROMPT,
            tools=tool_definitions,
            input=input_items,
            max_output_tokens=2000,
            prompt_cache_key="chess-coach-v1",
            store=False,
        )
        usage = getattr(response, "usage", None)
        input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        cached_tokens += int(getattr(input_details, "cached_tokens", 0) or 0)
        input_items += response.output
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if response.output_text:
                return CoachRunResult(
                    answer=response.output_text,
                    provider="openai",
                    model=settings.openai_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cached_tokens,
                    tool_rounds=round_index,
                )
            raise RuntimeError("Coach returned no text or tool calls")

        for call in calls:
            try:
                value = tools.execute(call.name, json.loads(call.arguments))
                output = json.dumps(value, default=str)
            except Exception as exc:
                output = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": output,
                }
            )
    raise RuntimeError("Coach exceeded the maximum number of tool rounds")


def _run_anthropic_loop(
    session: Session,
    tools: CoachTools,
    settings: Settings,
    *,
    message: str,
    history: list[dict],
) -> CoachRunResult:
    if not settings.anthropic_api_key:
        raise CoachUnavailable("ANTHROPIC_API_KEY is not configured")
    client = Anthropic(api_key=settings.anthropic_api_key)
    messages = history[-settings.coach_history_limit :] + [{"role": "user", "content": message}]
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_cost_usd = 0.0

    for round_index in range(settings.coach_max_tool_rounds):
        estimated_input_tokens = max(
            1,
            len(json.dumps([SYSTEM_PROMPT, TOOL_DEFINITIONS, messages], default=str)) // 3,
        )
        try:
            reservation = reserve_anthropic_call(
                session,
                settings,
                username=tools.user.username,
                maximum_cost_usd=estimate_anthropic_call_cost(
                    settings,
                    estimated_input_tokens=estimated_input_tokens,
                    max_output_tokens=1200,
                ),
            )
        except AiBudgetExceeded as exc:
            raise CoachUnavailable(str(exc)) from exc
        try:
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
        except AuthenticationError as exc:
            raise CoachUnavailable(
                "AI coach authentication failed. Update ANTHROPIC_API_KEY in Render."
            ) from exc
        except RateLimitError as exc:
            raise CoachUnavailable(
                "AI coach is temporarily rate-limited or out of API credit. Try again later."
            ) from exc
        except APIConnectionError as exc:
            raise CoachUnavailable("AI coach could not reach Anthropic. Try again later.") from exc
        except APIStatusError as exc:
            raise CoachUnavailable(
                f"AI coach provider returned HTTP {exc.status_code}. Try again later."
            ) from exc
        usage = getattr(response, "usage", None)
        call_input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        call_output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        call_cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        call_cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        call_cost_usd = anthropic_actual_cost(
            settings,
            input_tokens=call_input_tokens,
            output_tokens=call_output_tokens,
            cache_read_tokens=call_cache_read_tokens,
            cache_write_tokens=call_cache_write_tokens,
        )
        reconcile_anthropic_call(session, reservation, actual_cost_usd=call_cost_usd)
        total_cost_usd += call_cost_usd
        input_tokens += call_input_tokens
        output_tokens += call_output_tokens
        cache_read_tokens += call_cache_read_tokens
        cache_write_tokens += call_cache_write_tokens
        serialized = _serialize_content(response.content)
        messages.append({"role": "assistant", "content": serialized})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            return CoachRunResult(
                answer="\n".join(
                    block.text for block in response.content if block.type == "text"
                ),
                provider="anthropic",
                model=settings.anthropic_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                tool_rounds=round_index,
                cost_usd=total_cost_usd,
            )
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


def run_coach_loop(
    session: Session,
    settings: Settings,
    *,
    username: str,
    message: str,
    history: list[dict],
) -> CoachRunResult:
    tools = CoachTools(session, username)
    provider = settings.ai_provider.strip().lower()
    if provider == "openai":
        return _run_openai_loop(tools, settings, message=message, history=history)
    if provider == "anthropic":
        return _run_anthropic_loop(session, tools, settings, message=message, history=history)
    raise CoachUnavailable("AI_PROVIDER must be 'openai' or 'anthropic'")
