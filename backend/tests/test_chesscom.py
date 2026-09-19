from unittest.mock import AsyncMock

import httpx
import pytest

from app.ingestion.chesscom import ChessComClient, ChessComError


def make_client(handler, *, retries=0):
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ChessComClient(client=http_client, max_retries=retries), http_client


@pytest.mark.asyncio
async def test_get_archives_returns_urls():
    client, http_client = make_client(
        lambda _: httpx.Response(200, json={"archives": ["https://api.test/2026/09"]})
    )
    assert await client.get_archives("Player") == ["https://api.test/2026/09"]
    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_archives_maps_not_found():
    client, http_client = make_client(lambda _: httpx.Response(404))
    with pytest.raises(ChessComError, match="user not found"):
        await client.get_archives("missing")
    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_archives_defaults_to_empty_list():
    client, http_client = make_client(lambda _: httpx.Response(200, json={}))
    assert await client.get_archives("player") == []
    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_archive_returns_cache_validators():
    def handler(request):
        assert request.headers["if-none-match"] == '"old"'
        return httpx.Response(
            200,
            json={"games": [{"uuid": "one"}]},
            headers={"ETag": '"new"', "Last-Modified": "today"},
        )

    client, http_client = make_client(handler)
    result = await client.get_archive("https://api.test/archive", etag='"old"')
    assert result.games == [{"uuid": "one"}]
    assert result.etag == '"new"'
    assert result.last_modified == "today"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_archive_handles_not_modified():
    client, http_client = make_client(lambda _: httpx.Response(304))
    result = await client.get_archive("https://api.test/archive", etag='"same"')
    assert result.not_modified is True
    assert result.games == []
    await http_client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_retries_then_succeeds(monkeypatch):
    responses = iter([httpx.Response(429), httpx.Response(200, json={"archives": []})])
    client, http_client = make_client(lambda _: next(responses), retries=1)
    sleep = AsyncMock()
    monkeypatch.setattr("app.ingestion.chesscom.asyncio.sleep", sleep)
    assert await client.get_archives("player") == []
    sleep.assert_awaited_once()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_persistent_rate_limit_raises():
    client, http_client = make_client(lambda _: httpx.Response(429), retries=0)
    with pytest.raises(ChessComError, match="rate limit"):
        await client.get_archives("player")
    await http_client.aclose()


@pytest.mark.asyncio
async def test_server_error_is_not_hidden():
    client, http_client = make_client(lambda _: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_archives("player")
    await http_client.aclose()


@pytest.mark.asyncio
async def test_owned_client_closes_on_context_exit():
    client = ChessComClient()
    async with client:
        assert client.client.is_closed is False
    assert client.client.is_closed is True


@pytest.mark.asyncio
async def test_supplied_client_is_not_closed_on_context_exit():
    supplied = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    async with ChessComClient(client=supplied):
        pass
    assert supplied.is_closed is False
    await supplied.aclose()
