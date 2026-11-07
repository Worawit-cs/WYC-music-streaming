import pytest
from mutagen.mp4 import MP4

from wyc_music_streaming.library import Library
from wyc_music_streaming.rename import PartialRename, rename
from wyc_music_streaming.tags import TagData, read_tags, write_tags


@pytest.fixture
def env(config, make_audio):
    root = config.users["wick"].music_dir
    lib = Library(config.users)

    def add(rel, title, artist="MJ", album="Bad", track_artist=None, cover=None, tags=True):
        path = make_audio(root / rel)
        if tags:
            write_tags(path, TagData(title, track_artist or artist, album, artist, "aaaaaaaaaaa", cover_jpeg=cover))
        return path

    def run(**kw):
        result = rename(lib, config.users["wick"], **kw)
        return result

    def tree():
        lib.rescan("wick")
        return {(a["artist"], al["album"]): sorted(t["path"] for t in al["tracks"])
                for a in lib.tree("wick") for al in a["albums"]}

    return type("Env", (), {"root": root, "lib": lib, "add": staticmethod(add), "run": staticmethod(run),
                            "tree": staticmethod(tree)})


def test_rename_album_retags_moves_and_removes_old_folder(env):
    env.add("MJ/Bad/Bad.m4a", "Bad", cover=b"COVER")
    env.add("MJ/Bad/Smooth_Criminal.m4a", "Smooth Criminal")
    env.add("MJ/Thriller/Beat_It.m4a", "Beat It", album="Thriller")
    env.lib.rescan("wick")

    result = env.run(kind="album", artist="MJ", album="Bad", new_name="Bad (Special Edition)")

    assert (result.moved, result.merged) == (2, False)
    assert env.tree() == {
        ("MJ", "Bad (Special Edition)"): ["MJ/Bad_(Special_Edition)/Bad.m4a", "MJ/Bad_(Special_Edition)/Smooth_Criminal.m4a"],
        ("MJ", "Thriller"): ["MJ/Thriller/Beat_It.m4a"],
    }
    assert not (env.root / "MJ" / "Bad").exists()
    moved = env.root / "MJ/Bad_(Special_Edition)/Bad.m4a"
    tags = read_tags(moved)
    assert (tags["title"], tags["album"], tags["album_artist"], tags["video_id"]) == (
        "Bad", "Bad (Special Edition)", "MJ", "aaaaaaaaaaa")
    assert MP4(moved)["covr"][0] == b"COVER"


def test_rename_artist_keeps_feat_track_artists(env):
    env.add("linkinpark/Meteora/Numb.m4a", "Numb", artist="linkinpark", album="Meteora")
    env.add("linkinpark/Meteora/Faint.m4a", "Faint", artist="linkinpark", album="Meteora",
            track_artist="linkinpark feat. Jay-Z")
    env.lib.rescan("wick")

    result = env.run(kind="artist", artist="linkinpark", new_name="Linkin Park")

    assert result.moved == 2
    assert env.tree() == {("Linkin Park", "Meteora"): ["Linkin_Park/Meteora/Faint.m4a", "Linkin_Park/Meteora/Numb.m4a"]}
    numb = read_tags(env.root / "Linkin_Park/Meteora/Numb.m4a")
    faint = read_tags(env.root / "Linkin_Park/Meteora/Faint.m4a")
    assert (numb["artist"], numb["album_artist"]) == ("Linkin Park", "Linkin Park")
    assert (faint["artist"], faint["album_artist"]) == ("linkinpark feat. Jay-Z", "Linkin Park")
    assert not (env.root / "linkinpark").exists()


def test_merge_into_existing_artist_with_name_clash(env):
    env.add("The_Weeknd/Singles/One_Of_The_Girls.m4a", "One Of The Girls", artist="The Weeknd", album="Singles")
    env.add("The_Weeknd,_JENNIE_&_Lily_Rose_Depp/Singles/One_Of_The_Girls.m4a", "One Of The Girls",
            artist="The Weeknd, JENNIE & Lily Rose Depp", album="Singles")
    env.lib.rescan("wick")

    result = env.run(kind="artist", artist="The Weeknd, JENNIE & Lily Rose Depp", new_name="The Weeknd")

    assert (result.moved, result.merged) == (1, True)
    assert env.tree() == {("The Weeknd", "Singles"): [
        "The_Weeknd/Singles/One_Of_The_Girls.m4a", "The_Weeknd/Singles/One_Of_The_Girls_(2).m4a"]}


def test_untagged_files_get_tags_from_the_names_they_showed(env):
    env.add("MJ/Off_the_Wall/Rock_With_You.mp3", "x", tags=False)
    env.lib.rescan("wick")
    assert ("MJ", "Off_the_Wall") in env.tree()

    env.run(kind="album", artist="MJ", album="Off_the_Wall", new_name="Off the Wall")

    # Same folder after sanitizing: the file stays, only the tags change.
    assert env.tree() == {("MJ", "Off the Wall"): ["MJ/Off_the_Wall/Rock_With_You.mp3"]}
    tags = read_tags(env.root / "MJ/Off_the_Wall/Rock_With_You.mp3")
    assert (tags["album"], tags["album_artist"]) == ("Off the Wall", "MJ")


def test_crafted_name_stays_inside_music_dir(env):
    env.add("MJ/Bad/Bad.m4a", "Bad")
    env.lib.rescan("wick")
    env.run(kind="album", artist="MJ", album="Bad", new_name="../../etc")
    [(key, paths)] = env.tree().items()
    assert key == ("MJ", "../../etc")
    assert paths == ["MJ/etc/Bad.m4a"]


@pytest.mark.parametrize(
    ("kw", "error"),
    [
        ({"kind": "album", "artist": "MJ", "album": "Bad", "new_name": "  "}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": "Bad", "new_name": "Bad"}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": None, "new_name": "X"}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": "Nope", "new_name": "X"}, LookupError),
        ({"kind": "artist", "artist": "Nobody", "new_name": "X"}, LookupError),
    ],
)
def test_bad_requests(env, kw, error):
    env.add("MJ/Bad/Bad.m4a", "Bad")
    env.lib.rescan("wick")
    with pytest.raises(error):
        env.run(**kw)


def test_failure_midway_reports_moved_count_and_rescans(env, monkeypatch):
    env.add("MJ/Bad/A.m4a", "A")
    env.add("MJ/Bad/B.m4a", "B")
    env.lib.rescan("wick")
    import wyc_music_streaming.rename as mod

    real = mod.retag
    calls = []

    def flaky(path, **kw):
        calls.append(path)
        if len(calls) == 2:
            raise ValueError("disk said no")
        real(path, **kw)

    monkeypatch.setattr(mod, "retag", flaky)
    with pytest.raises(PartialRename) as info:
        env.run(kind="album", artist="MJ", album="Bad", new_name="Bad 2")
    assert info.value.moved == 1
    assert "disk said no" in str(info.value)
    # The index was rescanned without our help: one track moved, one did not.
    assert sorted(t.album for t in env.lib.tracks("wick")) == ["Bad", "Bad 2"]
    assert sum(len(p) for p in env.tree().values()) == 2
