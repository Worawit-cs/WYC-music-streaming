import json

import httpx
import pytest

from wyc_music_streaming.suggest import MAX_SUGGESTIONS, SUGGEST_URL, fetch_suggestions


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_returns_at_most_max_suggestions():
    seen = []

    def handler(request):
        seen.append(request)
        words = [f"the weeknd {i}" for i in range(10)]
        return httpx.Response(200, json=["the weeknd", words, [], {}])

    async with client_for(handler) as http:
        out = await fetch_suggestions(http, "the weeknd")
    assert out == [f"the weeknd {i}" for i in range(MAX_SUGGESTIONS)]
    [request] = seen
    assert str(request.url).startswith(SUGGEST_URL)
    assert request.url.params["q"] == "the weeknd"
    assert request.url.params["client"] == "firefox"
    assert request.url.params["ds"] == "yt"


async def test_keeps_thai_text():
    body = json.dumps(["เพลง", ["เพลงไทย", "เพลงฮิต"]], ensure_ascii=False).encode()

    def handler(request):
        return httpx.Response(200, content=body, headers={"Content-Type": "text/javascript; charset=UTF-8"})

    async with client_for(handler) as http:
        assert await fetch_suggestions(http, "เพลง") == ["เพลงไทย", "เพลงฮิต"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json=["q", ["x"]]),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"q": ["x"]}),
        httpx.Response(200, json=["q"]),
        httpx.Response(200, json=["q", "x"]),
    ],
    ids=["status-500", "bad-json", "dict", "short-list", "not-a-list"],
)
async def test_bad_responses_give_empty_list(response):
    async with client_for(lambda request: response) as http:
        assert await fetch_suggestions(http, "q") == []


async def test_drops_items_that_are_not_text():
    async with client_for(lambda request: httpx.Response(200, json=["q", ["ok", 3, None, " "]])) as http:
        assert await fetch_suggestions(http, "q") == ["ok"]


async def test_network_error_gives_empty_list():
    def handler(request):
        raise httpx.ConnectTimeout("too slow", request=request)

    async with client_for(handler) as http:
        assert await fetch_suggestions(http, "q") == []
