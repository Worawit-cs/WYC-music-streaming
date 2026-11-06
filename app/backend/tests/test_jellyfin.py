import asyncio

import httpx

from wyc_music_streaming.jellyfin import JellyfinClient, RefreshScheduler


def recorder(status=204):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    return httpx.MockTransport(handler), calls


async def test_refresh_sends_token_header():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    assert await client.refresh_library() is True
    [req] = calls
    assert req.method == "POST"
    assert req.url == "http://jf.test/Library/Refresh"
    assert req.headers["Authorization"] == 'MediaBrowser Token="KEY"'
    await client.aclose()


async def test_refresh_http_error_returns_false():
    transport, _ = recorder(status=500)
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    assert await client.refresh_library() is False
    await client.aclose()


async def test_refresh_offline_returns_false():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    client = JellyfinClient("http://jf.test", "KEY", transport=httpx.MockTransport(handler))
    assert await client.refresh_library() is False
    await client.aclose()


async def test_scheduler_coalesces_calls():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    scheduler = RefreshScheduler(client, delay=0.05)
    scheduler.schedule()
    scheduler.schedule()
    scheduler.schedule()
    await asyncio.sleep(0.15)
    assert len(calls) == 1
    scheduler.schedule()
    await asyncio.sleep(0.15)
    assert len(calls) == 2
    await scheduler.aclose()
    await client.aclose()


async def test_refresh_now_cancels_pending():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    scheduler = RefreshScheduler(client, delay=0.05)
    scheduler.schedule()
    assert await scheduler.refresh_now() is True
    await asyncio.sleep(0.15)
    assert len(calls) == 1
    await scheduler.aclose()
    await client.aclose()
