from wyc_music_streaming.auth import HEADER, resolve_user
from wyc_music_streaming.config import load_config


def test_known_login(config):
    assert resolve_user({HEADER: "wick@example.com"}, config).name == "wick"


def test_login_is_case_insensitive(config):
    assert resolve_user({HEADER: "Safeena@Example.COM"}, config).name == "safeena"


def test_unknown_login(config):
    assert resolve_user({HEADER: "stranger@example.com"}, config) is None


def test_missing_header(config):
    assert resolve_user({}, config) is None


def test_dev_mode_uses_dev_user_without_header(write_cfg):
    cfg = load_config(write_cfg(server_extra='dev = true\ndev_user = "wick"'))
    assert resolve_user({}, cfg).name == "wick"


def test_dev_mode_still_rejects_unknown_header(write_cfg):
    cfg = load_config(write_cfg(server_extra='dev = true\ndev_user = "wick"'))
    assert resolve_user({HEADER: "stranger@example.com"}, cfg) is None
