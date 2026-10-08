# Web File Viewer

A Dockerized web application for browsing a directory tree, viewing `.html` and Markdown files in the browser, and downloading any file.

- **Markdown** (`.md`, `.markdown`, `.mdown`, `.mkd`) is rendered as styled, GitHub-like HTML (tables, fenced code blocks, syntax highlighting). A raw view is available via `?raw=1`.
- **HTML** (`.html`, `.htm`) is served natively.
- **Text/code files** are displayed as plain text.
- **Any file** can be downloaded via the per-file Download button or `/download/<path>`.
- The mounted directory is served **read-only**. Dotfiles (`.ssh`, `.config`, etc.) are hidden by default. Path traversal and symlink escapes are blocked.

---

## Project Layout

```
webviewer/
├── docker-compose.yml   # Compose stack definition (port, volume mount)
├── Dockerfile           # python:3.12-slim + gunicorn
├── requirements.txt     # flask, markdown, pygments, gunicorn
└── app/
    ├── main.py          # Flask application
    ├── templates/       # Jinja2 templates
    └── static/          # CSS
```

---

## Prerequisites

- 64-bit Linux host (Ubuntu 22.04/24.04 or RHEL 8/9 and compatible: Rocky, AlmaLinux, CentOS Stream)
- A user with `sudo` privileges
- Outbound internet access (to pull base images and packages)

---

## 1. Install Docker Engine + Docker Compose

Docker Compose v2 is included as a plugin (`docker compose`) when installing Docker Engine from Docker's official repositories.

### Ubuntu (22.04 / 24.04)

```bash
# Remove any old/conflicting packages
sudo apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null

# Install repository prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the Docker apt repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker
sudo systemctl enable --now docker
```

### RHEL (8 / 9) and compatible (Rocky, AlmaLinux, CentOS Stream)

```bash
# Remove any old/conflicting packages (podman-docker conflicts with Docker CE)
sudo dnf remove -y docker docker-client docker-common docker-engine podman runc 2>/dev/null

# Add Docker's official repository
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
# On Rocky/AlmaLinux/CentOS Stream use the CentOS repo instead:
#   sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Install Docker Engine + Compose plugin
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker
sudo systemctl enable --now docker
```

### Post-install (both distros)

Run Docker without `sudo` by adding your user to the `docker` group:

```bash
sudo usermod -aG docker $USER
newgrp docker   # or log out and back in
```

Verify the installation:

```bash
docker --version          # e.g. Docker version 29.x
docker compose version    # e.g. Docker Compose version v5.x
docker run --rm hello-world
```

---

## 2. Configure the Viewer

Edit `docker-compose.yml` before first start:

```yaml
services:
  webviewer:
    build: .
    container_name: webviewer
    ports:
      - "8123:8000"            # host port : container port
    volumes:
      - /home/vs3:/data:ro     # directory to serve (read-only)
    environment:
      - ROOT_DIR=/data
      - SHOW_HIDDEN=false      # set true to show dotfiles
    restart: unless-stopped
```

| Setting | Where | Description |
|---|---|---|
| Served directory | `volumes` (left side of `:`) | **Set this to the absolute path you want to browse** (e.g. your home directory). Avoid `${HOME}` — it resolves to the home of whoever runs `docker compose` (e.g. `/root` under sudo). |
| Host port | `ports` (left side of `:`) | Default `8123`. Change if the port is in use. |
| Hidden files | `SHOW_HIDDEN` | `false` (default) hides dotfiles from listings and blocks direct access. |
| Write access | `:ro` suffix | Keep `ro` — the viewer never needs write access. |

> **RHEL + SELinux note:** if the container cannot read the mounted directory (`Permission denied` with SELinux enforcing), append the `z` option to the volume: `- /home/youruser:/data:ro,z` — or set an appropriate SELinux context on the source directory.

---

## 3. Build and Run

```bash
cd webviewer
docker compose up -d --build
```

Verify:

```bash
docker ps --filter name=webviewer        # should show "Up ... (healthy)"
curl -sL http://localhost:8123/healthz   # {"status":"ok"}
```

Open **http://localhost:8123** (or `http://<server-ip>:8123` from another machine).

### Firewall (remote access)

```bash
# Ubuntu (ufw)
sudo ufw allow 8123/tcp

# RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8123/tcp
sudo firewall-cmd --reload
```

---

## 4. Day-2 Operations

| Action | Command |
|---|---|
| Stop | `docker compose down` |
| Start | `docker compose up -d` |
| Rebuild after code changes | `docker compose up -d --build` |
| Apply compose file changes | `docker compose up -d --force-recreate` |
| Logs | `docker compose logs -f webviewer` |
| Status/health | `docker ps --filter name=webviewer` |

---

## URL Reference

| URL | Behavior |
|---|---|
| `/` | Redirects to the root listing |
| `/browse/<path>` | Directory listing, or file view (Markdown rendered, HTML served, text shown, binaries downloaded) |
| `/browse/<path>?raw=1` | Raw source for Markdown/HTML files |
| `/browse/<path>?download=1` | Force download |
| `/download/<path>` | Force download |
| `/healthz` | Health check (used by the container HEALTHCHECK) |

---

## Security Notes

- The mount is **read-only** — the viewer cannot modify, create, or delete files.
- **Path traversal** (`../`, URL-encoded variants) and **symlinks escaping the mount** are rejected with `403`.
- **Dotfiles** are hidden (404) unless `SHOW_HIDDEN=true`.
- There is **no authentication**. The viewer exposes your files to anyone who can reach the port — keep it on a trusted network, bind to `127.0.0.1:8123:8000` for local-only use, or put it behind an authenticating reverse proxy (nginx/Caddy/Traefik) for remote access.
- HTML files are served as-is by design; only browse directories whose contents you trust.
