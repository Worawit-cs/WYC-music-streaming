import pytest

from wyc_music_streaming.paths import (
    UnsafePath,
    safe_resolve,
    sanitize_name,
    track_filename,
    unique_path,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Numb", "Numb"),
        ('AC/DC: "Back" <In> Black?', "ACDC_Back_In_Black"),
        ("  spaced  ", "spaced"),
        ("Linkin Park", "Linkin_Park"),
        ("a  \t b", "a_b"),
        ("เพลง ไทย", "เพลง_ไทย"),
        ("x" * 119 + " y", "x" * 119),
        ("..", "Unknown"),
        ("", "Unknown"),
        ("a\x00b\nc", "abc"),
        ("x" * 200, "x" * 120),
        ("เพลงไทย", "เพลงไทย"),
    ],
)
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_sanitize_name_custom_fallback():
    assert sanitize_name("???", fallback="Singles") == "Singles"


def test_safe_resolve_inside(tmp_path):
    root = tmp_path / "music"
    (root / "A").mkdir(parents=True)
    assert safe_resolve(root, "A/x.m4a") == (root / "A" / "x.m4a").resolve()


@pytest.mark.parametrize("rel", ["../etc/passwd", "A/../../x.m4a", "/etc/passwd", "", "."])
def test_safe_resolve_rejects_escape(tmp_path, rel):
    root = tmp_path / "music"
    root.mkdir()
    with pytest.raises(UnsafePath):
        safe_resolve(root, rel)


def test_safe_resolve_rejects_symlink_escape(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(UnsafePath):
        safe_resolve(root, "link/x.m4a")


def test_unique_path(tmp_path):
    p = tmp_path / "a.m4a"
    assert unique_path(p) == p
    p.touch()
    assert unique_path(p) == tmp_path / "a_(2).m4a"
    (tmp_path / "a_(2).m4a").touch()
    assert unique_path(p) == tmp_path / "a_(3).m4a"


def test_track_filename():
    assert track_filename("Numb", "m4a") == "Numb.m4a"
    assert track_filename("Faint", "m4a", 7) == "07_Faint.m4a"
    assert track_filename("Smooth Operator", "opus") == "Smooth_Operator.opus"
    assert track_filename("a/b", "opus") == "ab.opus"
