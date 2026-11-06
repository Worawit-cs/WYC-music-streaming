# 🧠 WYC-music-streaming — Home NAS + Media Streaming Server

## 📌 Overview

This project is a self-hosted NAS (Network Attached Storage) combined with a media streaming server.

The system allows users to:

* Store files centrally
* Back up files
* Access data remotely via VPN
* Stream music smoothly using a dedicated media server

---

## 🚀 Features

* 📂 File storage via Samba (SMB)
* 🎵 Music streaming via Jellyfin
* 🌐 Secure remote access via Tailscale VPN
* 👥 Multi-user support with access control
* 🔐 Firewall protection using UFW

---

## 🏗️ Architecture

```
Client (iPad / PC / Phone)
        ↓
   Tailscale VPN
        ↓
   Ubuntu Server (NAS)
   ├── Samba (File Sharing)
   └── Jellyfin (Streaming)
```

---

## ⚙️ Tech Stack

* OS: Ubuntu (Lubuntu)
* File Sharing: Samba (SMB)
* Media Server: Jellyfin
* VPN: Tailscale
* Firewall: UFW

---

## 🛠️ Setup Guide

### 1. Install Samba

```
sudo apt install samba
```

---

### 2. Create Users

```
(Adding another user for your system)
sudo adduser friend1
sudo smbpasswd -a friend1
```

---

### 3. Setup Folder Structure

```
mkdir -p /home/username/share/public
mkdir -p /home/username/share/yourname
mkdir -p /home/username/share/friend1
```

---

### 4. Setup Permissions (Important)

Set ownership:

```
sudo chown -R username:username /home/username/share
```

Set permissions:

```
# Directories: rwx for owner and group; setgid so new files keep the group
sudo find /home/username/share -type d -exec chmod 2775 {} +
# Files: rw for owner and group, no execute bit
sudo find /home/username/share -type f -exec chmod 664 {} +
```

Add users to group:

```
sudo usermod -aG username friend1
sudo usermod -aG username jellyfin
```

> ⚠️ Samba access depends on underlying Linux file permissions.
>
> Avoid `chmod -R 775`: it marks every music file as executable.

---

### 5. Configure Samba

Main config file:

```
/etc/samba/smb.conf
```

Example configuration:

```ini
[public]
   path = /home/wick/share/public
   browseable = yes
   read only = no
   valid users = wick safeena
   create mask = 0660
   directory mask = 0770

[owner]
   path = /home/wick/share/owner
   browseable = no
   valid users = owner
   read only = no
   create mask = 0660
   directory mask = 0770

[friend1]
   path = /home/wick/share/friend1
   browseable = no
   # Optional: add owner so the admin can manage this share.
   valid users = friend1 owner
   read only = no
   create mask = 0660
   directory mask = 0770
```

> ⚠️ Samba does not support inline comments. Text after a value
> (e.g. `valid users = friend1 owner(admin)`) is read as part of the value,
> so `owner` would be denied. Put comments on their own line starting with `#`.

Full config: [configs/smb.conf](configs/smb.conf)

Test config:

```
testparm
```

Restart service:

```
sudo systemctl restart smbd
```

---

### 6. Install Jellyfin

```
sudo apt install jellyfin
```

Access web UI:

```
http://<server-ip>:8096
```

---

### 7. Setup VPN (Tailscale)

```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

---

### 8. Configure Firewall

```
sudo ufw allow 22
(samba)
sudo ufw allow from 192.168.1.0/24 to any port 445  (LAN)
sudo ufw allow from 100.64.0.0/10 to any port 445   (VPN)
(jellyfin)
sudo ufw allow from 192.168.1.0/24 to any port 8096 (LAN)
sudo ufw allow from 100.64.0.0/10 to any port 8096  (VPN)
```

---

## 📱 Usage

### Upload Files

* Access via SMB:

```
smb://<server-ip>
```
* Use apps like:

  * Files (iOS)
  * VLC
  * Windows Explorer

* Access in PC (Linux): see [Mount the NAS on Linux](#mount-the-nas-on-linux)

---

### Mount the NAS on Linux

The path after the IP is the **share name** from `smb.conf` (`public`, `wick`, `safeena`).

One-time mount (lost after reboot):

```
sudo apt install cifs-utils
sudo mkdir -p /mnt/nas
sudo mount -t cifs //<server-ip>/wick /mnt/nas -o username=wick,uid=$(id -u),gid=$(id -g)
```

Auto-mount on boot (no need to mount every time):

1. Create a credentials file readable only by root:

   ```
   sudo tee /root/.smbcredentials > /dev/null <<'EOF'
   username=wick
   password=<your-samba-password>
   EOF
   sudo chmod 600 /root/.smbcredentials
   ```

2. Add this line to `/etc/fstab` (replace `1000` with your `id -u` / `id -g`):

   ```
   //<server-ip>/wick  /mnt/nas  cifs  credentials=/root/.smbcredentials,uid=1000,gid=1000,_netdev,nofail,x-systemd.automount  0  0
   ```

3. Test:

   ```
   sudo systemctl daemon-reload
   sudo mount -a
   ls /mnt/nas
   ```

`x-systemd.automount` mounts the share on first access. `nofail` lets the PC boot when the NAS is off.

### Backup

Quote paths that contain spaces:

```
rsync -av "/home/<you>/<source dir>/" /mnt/nas/backup/
```

---

### Stream Music

* Use Jellyfin app
* Server:

```
http://<tailscale-ip>:8096
```

---

## 👥 User System

| User    | Role        |
| ------- | ----------- |
| wick    | Admin       |
| safeena | Normal user |

---

## 🔐 Permission Model

* Linux permissions control actual file access
* Samba only exposes shares
* Group-based access control is used

Example:

* wick → full access
* safeena → limited access

---

## 🧪 Troubleshooting

### ❌ Jellyfin cannot see files

Cause: Permission issue

Fix:

```
sudo usermod -aG wick jellyfin
sudo find /home/wick/share -type d -exec chmod 2775 {} +
sudo find /home/wick/share -type f -exec chmod 664 {} +
sudo systemctl restart jellyfin
```

Group membership applies only after the service restarts.

---

### ❌ SMB Permission denied

Fix:

```
sudo chown -R wick:wick /home/wick/share
```

---

### ❌ Slow streaming / buffering

Cause:

* Playing files directly via SMB

Fix:

* Use Jellyfin for streaming instead

---

## 📈 Future Improvements

* Add Fail2Ban for brute-force protection
* Setup automatic backup (rsync + cron)
* Add Nextcloud for web file access
* Use reverse proxy (NGINX)

---

## 💡 Key Learnings

* Linux permissions (user/group)
* Network file sharing (SMB)
* VPN networking
* Media streaming architecture
* System design & security fundamentals

---

## 🎯 Conclusion

This project demonstrates a real-world home server setup combining:

* Networking
* Security
* System administration

It provides a strong foundation for DevOps and security-related roles.

---

## 📸 Screenshots

* Jellyfin UI

<p align="center">
  <img src="images/jellyfin1.jpg" width="400">
</p>

<p align="center">
  <img src="images/jellyfin2.jpg" width="400">
</p>

* Samba folders
```
/home/wick/share/
    |
    |-> public/
    |
    |-> safeena/
           |
           |
           |-> music/
    |
    |-> wick/
         |
         |-> backup/
         |
         |-> music/
               |
               |-> linkinpark/
               |       |
               |       |-> hybrid/
               |       |
               |       |-> meteora/
               |
               |-> kanyewest/
               |
               |
               |-> otherpopularmusic/
               |
               |
               |-> phonk/
               |
               |
               |-> sade/
```
* Network diagram
  ![Network diagram](images/network-diagram.png)

---

## 🎵 Music downloader app

A web app on the NAS downloads music from YouTube straight into each user's
Jellyfin library. Setup and deploy: [app/README.md](app/README.md).
