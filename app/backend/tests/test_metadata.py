import pytest

from wyc_music_streaming.metadata import Suggested, clean


@pytest.mark.parametrize(
    ("title", "channel", "expected"),
    [
        ("Linkin Park - Numb (Official Music Video) [4K UPGRADE]", "Linkin Park",
         Suggested("Numb", "Linkin Park", "Singles")),
        ("Numb", "Linkin Park - Topic", Suggested("Numb", "Linkin Park", "Singles")),
        ("Sade - Smooth Operator (Official Video) | HD", "SadeVEVO",
         Suggested("Smooth Operator", "Sade", "Singles")),
        ("Kanye West - Stronger (Lyrics)", "Lyrics Channel",
         Suggested("Stronger", "Kanye West", "Singles")),
        ("Midnight City (Visualizer)", "M83VEVO", Suggested("Midnight City", "M83", "Singles")),
        ("Sade – Smooth Operator", "Some Channel", Suggested("Smooth Operator", "Sade", "Singles")),
        ("Faint (Official Audio)", "Linkin Park", Suggested("Faint", "Linkin Park", "Singles")),
        ("Numb [HD]", "Linkin Park", Suggested("Numb", "Linkin Park", "Singles")),
        ("Numb (Lyric Video)", "Linkin Park", Suggested("Numb", "Linkin Park", "Singles")),
        ("Linkin Park - Numb [Official Music Video]", "x", Suggested("Numb", "Linkin Park", "Singles")),
    ],
)
def test_clean_titles(title, channel, expected):
    assert clean(title, channel) == expected


def test_uses_ytdlp_artist_track_album_when_present():
    got = clean("whatever (Official Video)", "Linkin Park - Topic",
                artist="Linkin Park", track="Numb", album="Meteora")
    assert got == Suggested("Numb", "Linkin Park", "Meteora")


def test_strips_artist_prefix_matching_known_artist():
    got = clean("Linkin Park - Numb (Official Video)", "Linkin Park", artist="Linkin Park")
    assert got == Suggested("Numb", "Linkin Park", "Singles")


def test_playlist_title_is_default_album():
    got = clean("Some Phonk Track", "PhonkChannel", playlist_title="Phonk Mix")
    assert got == Suggested("Some Phonk Track", "PhonkChannel", "Phonk Mix")


def test_title_first_when_right_side_is_the_channel():
    # Real YouTube title seen in a dev run: "Title – Artist", uploaded by the artist.
    got = clean("Numb (Official Music Video) [4K UPGRADE] – Linkin Park", "Linkin Park")
    assert got == Suggested("Numb", "Linkin Park", "Singles")


def test_empty_values_get_fallbacks():
    assert clean("", "") == Suggested("Unknown", "Unknown Artist", "Singles")
