import pytest

from wyc_music_streaming.library import Library, scan_dir
from wyc_music_streaming.paths import UnsafePath
from wyc_music_streaming.tags import TagData, write_tags


@pytest.fixture
def tagged(make_audio):
    def _tagged(path, title, artist="Linkin Park", album="Meteora", video_id="kXYiU_JCYtU", track_no=None):
        make_audio(path)
        write_tags(path, TagData(title, artist, album, artist, video_id, track_no=track_no))
        return path
    return _tagged


def test_scan_reads_tags_and_falls_back_to_folders(config, make_audio, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "LP" / "Meteora" / "x.m4a", "Numb", track_no=13)
    make_audio(root / "Sade" / "Diamond Life" / "Smooth Operator.mp3")
    make_audio(root / ".wyc-music-streaming-tmp" / "9.m4a")
    (root / "notes.txt").write_text("not audio")

    tracks = {t.path: t for t in scan_dir(root)}

    assert set(tracks) == {"LP/Meteora/x.m4a", "Sade/Diamond Life/Smooth Operator.mp3"}
    t = tracks["LP/Meteora/x.m4a"]
    assert (t.title, t.artist, t.album, t.video_id, t.track_no) == ("Numb", "Linkin Park", "Meteora", "kXYiU_JCYtU", 13)
    u = tracks["Sade/Diamond Life/Smooth Operator.mp3"]
    assert (u.title, u.artist, u.album, u.video_id) == ("Smooth Operator", "Sade", "Diamond Life", None)


def test_file_at_root_uses_unknown_artist(config, make_audio):
    root = config.users["wick"].music_dir
    make_audio(root / "loose.m4a")
    [t] = scan_dir(root)
    assert (t.artist, t.album, t.title) == ("Unknown Artist", "Singles", "loose")


def test_index_tree_and_video_ids(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "13 Numb.m4a", "Numb", track_no=13, video_id="aaaaaaaaaaa")
    tagged(root / "Linkin Park" / "Meteora" / "07 Faint.m4a", "Faint", track_no=7, video_id="bbbbbbbbbbb")
    lib = Library(config.users)
    lib.rescan_all()

    tree = lib.tree("wick")
    assert [a["artist"] for a in tree] == ["Linkin Park"]
    [album] = tree[0]["albums"]
    assert album["album"] == "Meteora"
    assert [t["title"] for t in album["tracks"]] == ["Faint", "Numb"]
    assert lib.video_ids("wick") == {"aaaaaaaaaaa", "bbbbbbbbbbb"}
    assert lib.has_video("wick", "aaaaaaaaaaa")
    assert lib.tree("safeena") == []


def test_add_file_updates_index(config, tagged):
    lib = Library(config.users)
    lib.rescan_all()
    root = config.users["wick"].music_dir
    path = tagged(root / "Linkin Park" / "Singles" / "Numb.m4a", "Numb", album="Singles")
    track = lib.add_file("wick", path)
    assert track.path == "Linkin Park/Singles/Numb.m4a"
    assert lib.has_video("wick", "kXYiU_JCYtU")


def test_delete_removes_file_and_empty_dirs(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "Numb.m4a", "Numb")
    lib = Library(config.users)
    lib.rescan_all()

    lib.delete("wick", "Linkin Park/Meteora/Numb.m4a")

    assert not (root / "Linkin Park").exists()
    assert root.is_dir()
    assert lib.tracks("wick") == []


def test_delete_keeps_non_empty_album(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "Numb.m4a", "Numb", video_id="aaaaaaaaaaa")
    tagged(root / "Linkin Park" / "Meteora" / "Faint.m4a", "Faint", video_id="bbbbbbbbbbb")
    lib = Library(config.users)
    lib.rescan_all()

    lib.delete("wick", "Linkin Park/Meteora/Numb.m4a")

    assert (root / "Linkin Park" / "Meteora" / "Faint.m4a").exists()
    assert lib.video_ids("wick") == {"bbbbbbbbbbb"}


def test_delete_rejects_traversal(config):
    lib = Library(config.users)
    with pytest.raises(UnsafePath):
        lib.delete("wick", "../safeena-music/x.m4a")


def test_delete_missing_or_non_audio(config):
    root = config.users["wick"].music_dir
    (root / "notes.txt").write_text("x")
    lib = Library(config.users)
    with pytest.raises(FileNotFoundError):
        lib.delete("wick", "nope.m4a")
    with pytest.raises(FileNotFoundError):
        lib.delete("wick", "notes.txt")
