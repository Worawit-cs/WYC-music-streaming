# WYC-music-streaming app

Web app on the NAS. It downloads music from YouTube into each user's music
folder and refreshes Jellyfin. Design: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`.

## Dev machine

```
cd app/backend
uv sync --python 3.12
uv run pytest -q
```

Run locally with a dev config (`[server] dev = true`, `dev_user = "<name>"`):

```
WYC_MUSIC_STREAMING_CONFIG=/path/to/dev-config.toml uv run python -m wyc_music_streaming
```

Never use dev mode on the NAS.

## NAS: one-time setup

Quick way: run steps 2–7 with one script. It asks for the Tailscale logins and the Jellyfin key, and is safe to run again:

```
curl -fsSLO https://raw.githubusercontent.com/Worawit-cs/WYC-music-streaming/main/app/deploy/nas-setup.sh
bash nas-setup.sh          # as wick, not with sudo
```

The manual steps:

1. Preflight: `bash app/deploy/check-nas.sh` (from a clone, or after step 4).
2. Packages and tools (system-wide, so the service user can run them):

   ```
   sudo apt install ffmpeg unzip
   curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
   curl -fsSL https://deno.land/install.sh | sudo env DENO_INSTALL=/usr/local sh -s -- -y --no-modify-path
   deno --version
   ```

3. Service user and folders:

   ```
   sudo useradd --system --gid wick --home-dir /var/lib/wyc-music-streaming --create-home wyc-music-streaming
   sudo mkdir -p /opt/wyc-music-streaming /etc/wyc-music-streaming
   sudo chown wick: /opt/wyc-music-streaming
   ```

4. Code:

   ```
   git clone https://github.com/Worawit-cs/WYC-music-streaming.git /opt/wyc-music-streaming/repo
   ```

5. Config and Jellyfin key (Jellyfin Dashboard → API Keys → +):

   ```
   sudo install -m 640 -o root -g wick \
     /opt/wyc-music-streaming/repo/app/deploy/config.example.toml /etc/wyc-music-streaming/config.toml
   sudo nano /etc/wyc-music-streaming/config.toml      # set real tailscale_login values
   echo 'PASTE-KEY-HERE' | sudo tee /etc/wyc-music-streaming/jellyfin.key >/dev/null
   sudo chown root:wick /etc/wyc-music-streaming/jellyfin.key
   sudo chmod 640 /etc/wyc-music-streaming/jellyfin.key
   ```

6. Deploy: `sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh`
7. Tailscale (admin console: enable MagicDNS and HTTPS certificates first):

   ```
   sudo tailscale serve --bg --https=443 http://127.0.0.1:8097
   ```

Do not open port 8097 in UFW.

## Update

```
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
```

yt-dlp also updates itself weekly (`wyc-music-streaming-update-ytdlp.timer`).
To update it now: `sudo systemctl start wyc-music-streaming-update-ytdlp`.

## Logs

```
journalctl -u wyc-music-streaming -f
```
