from wyc_music_streaming.events import EventBroker, format_sse


async def test_publish_reaches_only_that_user():
    broker = EventBroker()
    wick = broker.subscribe("wick")
    safeena = broker.subscribe("safeena")
    broker.publish("wick", "job", {"id": 1})
    assert wick.get_nowait() == {"type": "job", "data": {"id": 1}}
    assert safeena.empty()


async def test_unsubscribe_stops_delivery():
    broker = EventBroker()
    q = broker.subscribe("wick")
    broker.unsubscribe("wick", q)
    broker.publish("wick", "job", {})
    assert q.empty()
    broker.unsubscribe("wick", q)  # second call is harmless


async def test_full_queue_drops_events():
    broker = EventBroker(maxsize=1)
    q = broker.subscribe("wick")
    broker.publish("wick", "job", {"n": 1})
    broker.publish("wick", "job", {"n": 2})
    assert q.qsize() == 1
    assert q.get_nowait()["data"] == {"n": 1}


def test_format_sse_keeps_thai_text():
    text = format_sse({"type": "library", "data": {"title": "เพลง"}})
    assert text == 'event: library\ndata: {"title": "เพลง"}\n\n'
