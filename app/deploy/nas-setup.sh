#!/usr/bin/env bash
# One-time NAS setup for WYC-music-streaming (app/README.md "NAS: one-time setup", steps 2-7).
# Run as the normal NAS user (wick), NOT with sudo:
#   curl -fsSLO https://raw.githubusercontent.com/Worawit-cs/WYC-music-streaming/main/app/deploy/nas-setup.sh
#   bash nas-setup.sh
# Safe to run again: every step skips work that is already done.
set -euo pipefail

BASE=/opt/wyc-music-streaming
REPO=$BASE/repo
ETC=/etc/wyc-music-streaming
SVC_USER=wyc-music-streaming
GROUP=wick
REPO_URL=https://github.com/Worawit-cs/WYC-music-streaming.git
PORT=8097

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "Run as your normal user (wick), not with sudo. The script calls sudo itself."
sudo -v

step "2. Packages and tools"
sudo apt-get install -y ffmpeg unzip git curl
if [[ ! -x /usr/local/bin/uv ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
fi
if [[ ! -x /usr/local/bin/deno ]]; then
  curl -fsSL https://deno.land/install.sh | sudo env DENO_INSTALL=/usr/local sh -s -- -y --no-modify-path
fi
/usr/local/bin/uv --version
/usr/local/bin/deno --version | head -1

step "3. Service user and folders"
getent group "$GROUP" >/dev/null || die "group '$GROUP' does not exist"
if ! id "$SVC_USER" >/dev/null 2>&1; then
  sudo useradd --system --gid "$GROUP" --home-dir "/var/lib/$SVC_USER" --create-home "$SVC_USER"
fi
sudo mkdir -p "$BASE" "$ETC"
sudo chown "$USER": "$BASE"
id "$SVC_USER"

step "4. Code"
if [[ -d $REPO/.git ]]; then
  echo "repo already cloned: $REPO"
else
  git clone "$REPO_URL" "$REPO"
fi

step "5a. Config"
if sudo test -f "$ETC/config.toml"; then
  echo "config exists, not touching it: $ETC/config.toml"
else
  read -rp "Tailscale login for wick    (e.g. name@gmail.com): " LOGIN_WICK
  read -rp "Tailscale login for safeena (e.g. name@gmail.com): " LOGIN_SAFEENA
  [[ -n $LOGIN_WICK && -n $LOGIN_SAFEENA ]] || die "both logins are required"
  tmp=$(mktemp)
  sed -e "s|tailscale_login = \"wick@gmail.com\"|tailscale_login = \"$LOGIN_WICK\"|" \
      -e "s|tailscale_login = \"safeena@gmail.com\"|tailscale_login = \"$LOGIN_SAFEENA\"|" \
      "$REPO/app/deploy/config.example.toml" > "$tmp"
  sudo install -m 640 -o root -g "$GROUP" "$tmp" "$ETC/config.toml"
  rm -f "$tmp"
  echo "written: $ETC/config.toml (edit later with: sudo nano $ETC/config.toml)"
fi

step "5b. Jellyfin API key"
if sudo test -s "$ETC/jellyfin.key"; then
  echo "key exists, not touching it: $ETC/jellyfin.key"
else
  echo "Jellyfin Dashboard -> API Keys -> + . Paste the key (input is hidden):"
  read -rs KEY; echo
  [[ -n $KEY ]] || die "empty key"
  printf '%s\n' "$KEY" | sudo sh -c "umask 027; cat > '$ETC/jellyfin.key'"
  unset KEY
  sudo chown "root:$GROUP" "$ETC/jellyfin.key"
  sudo chmod 640 "$ETC/jellyfin.key"
  echo "written: $ETC/jellyfin.key"
fi

step "5c. Music folders must be writable by $SVC_USER"
bad=0
while read -r dir; do
  if ! sudo test -d "$dir"; then
    echo "MISSING  $dir"; bad=1
  elif ! sudo -u "$SVC_USER" test -w "$dir" -a -x "$dir"; then
    echo "NO WRITE $dir"
    echo "         fix: sudo chgrp -R $GROUP '$dir' && sudo chmod -R g+rwX '$dir' && sudo find '$dir' -type d -exec chmod g+s {} +"
    bad=1
  else
    echo "OK       $dir"
  fi
done < <(sudo sed -n 's/^music_dir *= *"\(.*\)".*/\1/p' "$ETC/config.toml")
[[ $bad -eq 0 ]] || die "fix the music folders above, then run this script again"

step "6. Deploy"
sudo "$REPO/app/deploy/update.sh"

step "7. Tailscale serve (needs MagicDNS + HTTPS certificates enabled in the admin console)"
sudo tailscale serve --bg --https=443 "http://127.0.0.1:$PORT"
sudo tailscale serve status

step "Smoke check (local)"
# The service needs a few seconds to start (it scans the music folders first).
for _ in $(seq 30); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/api/me" && break
  sleep 1
done
LOGIN=$(sudo sed -n 's/^tailscale_login *= *"\(.*\)".*/\1/p' "$ETC/config.toml" | head -1)
echo "no header (expect 401 or 403):"
curl -s -o /dev/null -w '  HTTP %{http_code}\n' "http://127.0.0.1:$PORT/api/me" || true
echo "as $LOGIN (expect 200):"
curl -s -w '\n  HTTP %{http_code}\n' -H "Tailscale-User-Login: $LOGIN" "http://127.0.0.1:$PORT/api/me" || true
bash "$REPO/app/deploy/check-nas.sh" || true

step "Done"
echo "Logs: journalctl -u $SVC_USER -f"
