from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


class ChessComError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchiveResponse:
    url: str
    games: list[dict]
    etag: str | None
    last_modified: str | None
    not_modified: bool = False


class ChessComClient:
    base_url = "https://api.chess.com/pub"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "chess-coach/0.1 (github.com/bdrapeau-poly-crypto/chess-coach)",
        max_retries: int = 3,
    ) -> None:
        self._owned_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            http2=True,
        )
        self.max_retries = max_retries

    async def __aenter__(self) -> ChessComClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owned_client:
            await self.client.aclose()

    async def _get(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            response = await self.client.get(url, headers=headers)
            if response.status_code != 429:
                return response
            if attempt == self.max_retries:
                break
            retry_after = response.headers.get("Retry-After")
            delay = min(float(retry_after), 30.0) if retry_after else 2**attempt
            await asyncio.sleep(delay)
        raise ChessComError("Chess.com rate limit persisted after retries")

    async def get_archives(self, username: str) -> list[str]:
        url = f"{self.base_url}/player/{username.lower()}/games/archives"
        response = await self._get(url)
        if response.status_code == 404:
            raise ChessComError(f"Chess.com user not found: {username}")
        response.raise_for_status()
        archives = response.json().get("archives", [])
        return [str(item) for item in archives]

    async def get_archive(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> ArchiveResponse:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = await self._get(url, headers=headers)
        if response.status_code == 304:
            return ArchiveResponse(url, [], etag, last_modified, not_modified=True)
        response.raise_for_status()
        return ArchiveResponse(
            url=url,
            games=list(response.json().get("games", [])),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
