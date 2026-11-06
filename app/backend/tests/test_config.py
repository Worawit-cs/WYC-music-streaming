import pytest

from wyc_music_streaming.config import ConfigError, load_config


def test_loads_users_and_defaults(config, tmp_path):
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8097
    assert config.server.data_dir == tmp_path / "data"
    assert config.server.dev is False
    assert config.jellyfin.url == "http://jellyfin.test"
    assert config.jellyfin.api_key == "test-key"
    assert config.concurrency == 2
    wick = config.users["wick"]
    assert wick.tailscale_login == "wick@example.com"
    assert wick.music_dir == tmp_path / "wick-music"
    assert wick.jellyfin_user == "wick"
    assert config.users["safeena"].jellyfin_user is None


def test_user_by_login_is_case_insensitive(config):
    assert config.user_by_login("WICK@example.com").name == "wick"
    assert config.user_by_login(" safeena@example.com ").name == "safeena"
    assert config.user_by_login("stranger@example.com") is None


def test_rejects_non_loopback_host(write_cfg):
    with pytest.raises(ConfigError, match="loopback"):
        load_config(write_cfg(server_extra='host = "0.0.0.0"'))


def test_non_loopback_host_allowed_in_dev_mode(write_cfg):
    cfg = load_config(write_cfg(server_extra='host = "0.0.0.0"\ndev = true\ndev_user = "wick"'))
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.dev_user == "wick"


def test_rejects_missing_music_dir(write_cfg):
    users = '[users.x]\ntailscale_login = "x@example.com"\nmusic_dir = "/nonexistent/wyc-test"'
    with pytest.raises(ConfigError, match="music_dir does not exist"):
        load_config(write_cfg(users=users))


def test_rejects_duplicate_login(write_cfg, tmp_path):
    users = f"""
[users.a]
tailscale_login = "same@example.com"
music_dir = "{tmp_path / 'wick-music'}"
[users.b]
tailscale_login = "SAME@example.com"
music_dir = "{tmp_path / 'safeena-music'}"
"""
    with pytest.raises(ConfigError, match="duplicate tailscale_login"):
        load_config(write_cfg(users=users))


def test_rejects_missing_key_file(write_cfg, tmp_path):
    path = write_cfg()
    (tmp_path / "jellyfin.key").unlink()
    with pytest.raises(ConfigError, match="api_key_file not readable"):
        load_config(path)


def test_rejects_unknown_dev_user(write_cfg):
    with pytest.raises(ConfigError, match="dev_user"):
        load_config(write_cfg(server_extra='dev = true\ndev_user = "nobody"'))


def test_rejects_bad_concurrency(write_cfg, tmp_path):
    path = write_cfg()
    path.write_text(path.read_text().replace("concurrency = 2", "concurrency = 9"))
    with pytest.raises(ConfigError, match="concurrency"):
        load_config(path)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")
