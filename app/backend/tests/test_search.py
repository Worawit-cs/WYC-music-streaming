import pytest

from wyc_music_streaming.search import MAX_PLAYLIST, search


def fake(info):
    calls = []

    def extract(target, opts):
        calls.append((target, opts))
        return info

    return extract, calls


def test_keyword_search_uses_ytsearch10_flat():
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
    assert target == "ytsearch10:numb"
    assert opts["extract_flat"] == "in_playlist"
    assert out["kind"] == "search"
    assert out["playlist_title"] is None
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
