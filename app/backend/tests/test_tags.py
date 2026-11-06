import pytest
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus

from wyc_music_streaming.tags import TagData, read_tags, write_tags

FULL = TagData(
    title="Faint", artist="Linkin Park", album="Meteora", album_artist="Linkin Park",
    video_id="kXYiU_JCYtU", track_no=7, year="2003", cover_jpeg=b"COVER",
)


def test_m4a_round_trip(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.m4a")
    write_tags(path, FULL)
    got = read_tags(path)
    assert {k: got[k] for k in ("title", "artist", "album", "album_artist", "year", "track_no", "video_id")} == {
        "title": "Faint", "artist": "Linkin Park", "album": "Meteora", "album_artist": "Linkin Park",
        "year": "2003", "track_no": 7, "video_id": "kXYiU_JCYtU",
    }
    assert got["duration"] == pytest.approx(1.0, abs=0.2)
    assert MP4(path)["covr"][0] == b"COVER"


def test_opus_round_trip(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.opus")
    write_tags(path, FULL)
    got = read_tags(path)
    assert got["title"] == "Faint"
    assert got["album_artist"] == "Linkin Park"
    assert got["track_no"] == 7
    assert got["video_id"] == "kXYiU_JCYtU"
    assert OggOpus(path)["metadata_block_picture"]


def test_minimal_tags_without_optional_fields(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.m4a")
    write_tags(path, TagData("Numb", "Linkin Park", "Singles", "Linkin Park", "kXYiU_JCYtU"))
    got = read_tags(path)
    assert got["track_no"] is None
    assert got["year"] is None
    assert "covr" not in MP4(path)


def test_read_untagged_mp3(make_audio, tmp_path):
    got = read_tags(make_audio(tmp_path / "a.mp3"))
    assert got["title"] is None
    assert got["video_id"] is None
    assert got["duration"] == pytest.approx(1.0, abs=0.2)


def test_read_non_audio_returns_empty(tmp_path):
    p = tmp_path / "x.m4a"
    p.write_bytes(b"not audio")
    assert read_tags(p) == {}


def test_write_unsupported_container(make_audio, tmp_path):
    with pytest.raises(ValueError, match="unsupported container"):
        write_tags(make_audio(tmp_path / "a.mp3"), FULL)
