#!/usr/bin/env bash
# Deploy or update WYC-music-streaming on the NAS. Safe to run again.
# Usage: sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
set -euo pipefail

BASE=/opt/wyc-music-streaming
REPO=$BASE/repo
APP=$REPO/app
SVC=wyc-music-streaming

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
OWNER=$(stat -c %U "$REPO")

as_owner() {
  sudo -u "$OWNER" -H env UV_PYTHON_INSTALL_DIR="$BASE/python" bash -lc "$1"
}

echo "== git pull"
as_owner "git -C '$REPO' pull --ff-only"

echo "== backend"
as_owner "cd '$APP/backend' && uv sync --frozen --no-dev --python 3.12 \
  && uv pip install --python .venv/bin/python -U 'yt-dlp[default]'"

if [[ -f $APP/frontend/package.json ]]; then
  echo "== frontend"
  as_owner "source ~/.nvm/nvm.sh && cd '$APP/frontend' && npm ci && npm run build"
fi

echo "== deno"
deno upgrade || echo "warning: deno upgrade failed; continuing" >&2

echo "== systemd"
install -m 644 "$APP/deploy/$SVC.service" \
               "$APP/deploy/$SVC-update-ytdlp.service" \
               "$APP/deploy/$SVC-update-ytdlp.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "$SVC-update-ytdlp.timer"
systemctl enable "$SVC"
systemctl restart "$SVC"
sleep 2
systemctl --no-pager --lines=10 status "$SVC"
