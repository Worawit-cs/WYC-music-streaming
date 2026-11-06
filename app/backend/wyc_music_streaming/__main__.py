"""Entry point: python -m wyc_music_streaming"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .config import ConfigError, load_config
from .main import create_app

CONFIG_ENV = "WYC_MUSIC_STREAMING_CONFIG"
DEFAULT_CONFIG = "/etc/wyc-music-streaming/config.toml"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(2)
    # host comes from the validated config, so the loopback check in config.py really applies.
    uvicorn.run(create_app(config), host=config.server.host, port=config.server.port,
                proxy_headers=False, log_level="info")


if __name__ == "__main__":
    main()
