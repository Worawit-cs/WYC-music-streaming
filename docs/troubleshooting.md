# Troubleshooting

## Jellyfin cannot see files

Cause: permission issue. The `jellyfin` user cannot read the music folders.

Fix:

```
sudo usermod -aG wick jellyfin
sudo find /home/wick/share -type d -exec chmod 2775 {} +
sudo find /home/wick/share -type f -exec chmod 664 {} +
sudo systemctl restart jellyfin
```

Group membership applies only after the service restarts.

---

## SMB permission denied

Fix ownership:

```
sudo chown -R wick:wick /home/wick/share
```

If one user is denied on one share, check `valid users` in `smb.conf`.
Samba does not support inline comments: `valid users = safeena wick(admin)`
denies `wick`. Put comments on their own line, then run `testparm`.

---

## Mount fails with "No such file or directory"

The path after the IP must be a share name (`public`, `wick`, `safeena`),
not a folder name such as `share`.

---

## Slow streaming / buffering

Cause: playing files directly over SMB.

Fix: stream through Jellyfin instead.
