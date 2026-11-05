# Useful Commands

## Mount NAS (one-time)

The path after the IP is the share name from `smb.conf` (`public`, `wick`, `safeena`).

```
sudo mount -t cifs //<server-ip>/wick /mnt/nas -o username=wick,uid=$(id -u),gid=$(id -g)
```

For auto-mount on boot, see "Mount the NAS on Linux" in the [README](../README.md#mount-the-nas-on-linux).

## Backup

```
rsync -av "/home/<you>/<source dir>/" /mnt/nas/backup/
```

## Firewall

Allow Samba and Jellyfin only from LAN and Tailscale, not from everywhere:

```
sudo ufw allow 22
sudo ufw allow from 192.168.1.0/24 to any port 445
sudo ufw allow from 100.64.0.0/10  to any port 445
sudo ufw allow from 192.168.1.0/24 to any port 8096
sudo ufw allow from 100.64.0.0/10  to any port 8096
sudo ufw enable
sudo ufw status numbered
```

## Samba

```
testparm                      # check smb.conf syntax
sudo systemctl restart smbd
sudo smbpasswd -a <user>      # add Samba password for a Linux user
```
