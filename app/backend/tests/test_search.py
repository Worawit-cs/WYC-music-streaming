import pytest

from wyc_music_streaming.search import MAX_PAGES, MAX_PLAYLIST, PAGE_SIZE, search


def fake(info):
    calls = []

    def extract(target, opts):
        calls.append((target, opts))
        return info

    return extract, calls


def test_keyword_search_asks_for_page_one_flat():
    extract, calls = fake({
        "_type": "playlist", "title": "numb",
        "entries": [
            {"id": "kXYiU_JCYtU", "title": "Linkin Park - Numb (Official Music Video)",
             "channel": "Linkin Park", "duration": 187},
            {"id": "not-a-video-id"},
            None,
        ],
    })
    out = search("  numb  ", {"kXYiU_JCYtU"}, extract)
    [(target, opts)] = calls
    assert target == "ytsearch50:numb"
    assert opts["playlist_items"] == "1-10"
    assert opts["extract_flat"] == "in_playlist"
    assert out["kind"] == "search"
    assert out["playlist_title"] is None
    assert out["page"] == 1
    assert out["has_more"] is False  # only one valid entry came back
    [r] = out["results"]
    assert r == {
        "video_id": "kXYiU_JCYtU",
        "title": "Linkin Park - Numb (Official Music Video)",
        "channel": "Linkin Park",
        "duration": 187,
        "thumbnail_url": "https://i.ytimg.com/vi/kXYiU_JCYtU/mqdefault.jpg",
        "suggested": {"title": "Numb", "artist": "Linkin Park", "album": "Singles"},
        "in_library": True,
    }


def test_single_video_url_uses_ytdlp_music_fields():
    extract, calls = fake({
        "id": "4TYv2PhG89A", "title": "Sade - Smooth Operator - Official - 1984",
        "uploader": "Sade", "duration": 258,
        "artist": "Sade", "track": "Smooth Operator", "album": "Diamond Life",
    })
    out = search("https://www.youtube.com/watch?v=4TYv2PhG89A", set(), extract)
    assert calls[0][0] == "https://www.youtube.com/watch?v=4TYv2PhG89A"
    assert out["kind"] == "url"
    [r] = out["results"]
    assert r["channel"] == "Sade"
    assert r["suggested"] == {"title": "Smooth Operator", "artist": "Sade", "album": "Diamond Life"}
    assert r["in_library"] is False


def test_playlist_url_uses_playlist_title_as_album():
    extract, calls = fake({
        "_type": "playlist", "title": "Phonk Mix",
        "entries": [{"id": "aaaaaaaaaaa", "title": "Drift Phonk", "channel": "PhonkGuy"}],
    })
    out = search("https://music.youtube.com/playlist?list=PL1234567890", set(), extract)
    assert calls[0][1]["playlistend"] == MAX_PLAYLIST
    assert out["kind"] == "playlist"
    assert out["playlist_title"] == "Phonk Mix"
    assert out["results"][0]["suggested"]["album"] == "Phonk Mix"


def test_radio_mix_url_is_treated_as_single_video():
    extract, calls = fake({"id": "aaaaaaaaaaa", "title": "x", "channel": "y"})
    search("https://www.youtube.com/watch?v=aaaaaaaaaaa&list=RDaaaaaaaaaaa", set(), extract)
    assert calls[0][1]["noplaylist"] is True


def test_blank_query_raises():
    extract, _ = fake({})
    with pytest.raises(ValueError):
        search("   ", set(), extract)


def page_of(n):
    return {"_type": "playlist", "title": "q", "entries": [
        {"id": f"vid{i:08d}", "title": f"Song {i}", "channel": "Ch"} for i in range(n)
    ]}


def test_page_three_asks_for_items_21_to_30():
    extract, calls = fake(page_of(PAGE_SIZE))
    out = search("weeknd", set(), extract, page=3)
    assert calls[0][1]["playlist_items"] == "21-30"
    assert out["page"] == 3
    assert out["has_more"] is True


def test_last_page_has_no_more():
    extract, _ = fake(page_of(PAGE_SIZE))
    out = search("weeknd", set(), extract, page=MAX_PAGES)
    assert out["has_more"] is False


def test_short_page_has_no_more():
    extract, _ = fake(page_of(PAGE_SIZE - 1))
    assert search("weeknd", set(), extract, page=2)["has_more"] is False


@pytest.mark.parametrize("page", [0, MAX_PAGES + 1])
def test_page_out_of_range_raises(page):
    extract, _ = fake(page_of(1))
    with pytest.raises(ValueError):
        search("weeknd", set(), extract, page=page)


def test_url_lookup_ignores_page():
    extract, calls = fake({"id": "aaaaaaaaaaa", "title": "x", "channel": "y"})
    out = search("https://youtu.be/aaaaaaaaaaa", set(), extract, page=4)
    assert "playlist_items" not in calls[0][1]
    assert out["page"] == 1
    assert out["has_more"] is False
