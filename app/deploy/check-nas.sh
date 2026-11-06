#!/usr/bin/env bash
# Read-only preflight checks for WYC-music-streaming on the NAS.
# Usage: bash app/deploy/check-nas.sh
# Changes nothing. Exit code 1 means at least one required check failed.

FAILED=0
ok()   { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; FAILED=1; }

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg: $(ffmpeg -version | head -n1)"
else
  bad "ffmpeg missing. Fix: sudo apt install ffmpeg"
fi

if [[ -x /usr/local/bin/deno ]]; then
  ok "deno (system-wide): $(/usr/local/bin/deno --version | head -n1)"
else
  bad "deno not in /usr/local/bin. The service user cannot see ~/.deno. See app/README.md"
fi

if [[ -x /usr/local/bin/uv ]]; then
  ok "uv (system-wide): $(/usr/local/bin/uv --version)"
else
  bad "uv not in /usr/local/bin. See app/README.md"
fi

if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.nvm/nvm.sh"
  if command -v node >/dev/null 2>&1 && node -e 'process.exit(0)' 2>/dev/null; then
    ok "node: $(node --version) (needed by Plan 2 frontend build)"
  else
    warn "nvm found but node does not run. Try: nvm install --lts"
  fi
else
  warn "nvm missing (needed by Plan 2 frontend build only)"
fi

if command -v tailscale >/dev/null 2>&1; then
  ok "tailscale: $(tailscale version | head -n1)"
  serve_status="$(tailscale serve status 2>&1)"
  if grep -q '127.0.0.1:8097' <<<"$serve_status"; then
    ok "tailscale serve proxies to 127.0.0.1:8097"
  else
    warn "tailscale serve is not set up yet. After deploy: sudo tailscale serve --bg --https=443 http://127.0.0.1:8097"
  fi
else
  bad "tailscale missing"
fi

if sudo -n true 2>/dev/null; then
  ufw_status="$(sudo -n ufw status 2>&1)"
  if grep -qE '^8097' <<<"$ufw_status"; then
    bad "UFW has a rule for port 8097. Remove it: the app must not be reachable directly"
  else
    ok "UFW has no rule for port 8097"
  fi
else
  warn "skipped UFW check (needs sudo). Run: sudo -v && bash $0"
fi

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':8097$' | grep -vqE '^(127\.0\.0\.1|\[::1\]):8097$'; then
  bad "something listens on port 8097 on a non-loopback address"
else
  ok "nothing listens on port 8097 outside loopback"
fi

jf_version="$(curl -s --max-time 5 http://127.0.0.1:8096/System/Info/Public | grep -o '"Version":"[^"]*"')"
if [[ -n "$jf_version" ]]; then
  ok "jellyfin $jf_version"
else
  bad "jellyfin does not answer on http://127.0.0.1:8096"
fi

exit "$FAILED"
