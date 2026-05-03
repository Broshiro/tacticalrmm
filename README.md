# Broshiro RMM

> A self-hosted **Managed Services Platform** built on [TacticalRMM](https://github.com/amidaware/tacticalrmm).  
> This fork adds professional MSP-grade tooling on top of the solid upstream foundation: shared clipboard in remote sessions, Vaultwarden credential integration, a full automation engine, patch compliance reporting, Zammad ticketing, and more.

---

## Table of Contents

1. [What This Fork Adds](#what-this-fork-adds)
2. [Architecture Overview](#architecture-overview)
3. [Server Requirements](#server-requirements)
4. [DNS Requirements](#dns-requirements)
5. [Fresh Install — New Server](#fresh-install--new-server)
   - [Step 1 — Provision & Prepare the Server](#step-1--provision--prepare-the-server)
   - [Step 2 — Run the Official TRMM Installer](#step-2--run-the-official-trmm-installer)
   - [Step 3 — Swap Backend to This Fork](#step-3--swap-backend-to-this-fork)
   - [Step 4 — Install Fork Dependencies](#step-4--install-fork-dependencies)
   - [Step 5 — Run Fork Migrations](#step-5--run-fork-migrations)
   - [Step 6 — Build and Deploy the Custom Frontend](#step-6--build-and-deploy-the-custom-frontend)
   - [Step 7 — Restart Services](#step-7--restart-services)
6. [Migrating an Existing TRMM Server](#migrating-an-existing-trmm-server)
7. [Vaultwarden Integration Setup](#vaultwarden-integration-setup)
   - [Create an API Key in Vaultwarden](#create-an-api-key-in-vaultwarden)
   - [Configure Environment Variables](#configure-environment-variables)
   - [Organising Credentials by Client](#organising-credentials-by-client)
8. [Remote Session Features](#remote-session-features)
   - [Clipboard Sync](#clipboard-sync)
   - [Send as Keystrokes](#send-as-keystrokes)
   - [Credential Panel](#credential-panel)
9. [Environment Variable Reference](#environment-variable-reference)
10. [Updating the Fork](#updating-the-fork)
11. [Pulling Upstream Changes](#pulling-upstream-changes)
12. [Planned Features & Roadmap](#planned-features--roadmap)
13. [Development Setup](#development-setup)
14. [Contributing](#contributing)
15. [License](#license)

---

## What This Fork Adds

| # | Feature | Status |
|---|---------|--------|
| 7 | **Shared clipboard** — one-click sync from local browser to remote machine | ✅ Implemented |
| 8 | **Vaultwarden credential panel** — per-client credential sidebar in remote sessions | ✅ Implemented |
| 9 | **Send as keystrokes** — inject text or passwords directly into remote sessions | ✅ Implemented |
| 10 | Remove agent overdue checkmarks from agent list | 🔨 In Progress |
| 11 | Sites optional on client creation | 🔨 In Progress |
| 13 | Full automation engine — scheduled scripts with client/site/device-type scope | 📋 Planned |
| 14 | Extended email & SMS alerting | 📋 Planned |
| 15 | Zammad ticketing integration | 📋 Planned |
| 16 | Patch compliance reporting | 📋 Planned |
| 17 | Agent custom fields (SSD/HDD, gateway vendor, IP, etc.) | 📋 Planned |
| 18 | Onboarding profiles — auto-install AV and management software on agent enroll | 📋 Planned |

All upstream TacticalRMM features are preserved unchanged.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                     Browser (Technician)                   │
│                                                            │
│   Vue/Quasar SPA ── Broshiro/tacticalrmm-web               │
│   (served by nginx from /var/www/rmm/dist/)                │
└────────────────────┬───────────────────────────────────────┘
                     │ HTTPS REST API
┌────────────────────▼───────────────────────────────────────┐
│               Django Backend  (this repo)                  │
│               Broshiro/tacticalrmm                         │
│                                                            │
│   /rmm/api/  ── Python venv ── Celery workers              │
│   PostgreSQL ── Redis ── NATS                              │
└────────────────────┬───────────────────────────────────────┘
                     │ MeshCentral WebSocket / signed URL
┌────────────────────▼───────────────────────────────────────┐
│                   MeshCentral                              │
│           Remote desktop, terminal, file transfer          │
└────────────────────┬───────────────────────────────────────┘
                     │ NATS / TCP agent protocol
┌────────────────────▼───────────────────────────────────────┐
│                  Managed Endpoints                         │
│          Windows · Linux · macOS agents                    │
└────────────────────────────────────────────────────────────┘

   Optional integrations (same server or separate):
   ┌────────────────┐   ┌──────────────┐   ┌────────────────┐
   │  Vaultwarden   │   │    Zammad    │   │  SMTP / Twilio │
   │  (credentials) │   │ (ticketing)  │   │   (alerting)   │
   └────────────────┘   └──────────────┘   └────────────────┘
```

**Two GitHub repos are required:**

| Repo | Purpose |
|------|---------|
| `Broshiro/tacticalrmm` | Django REST API backend |
| `Broshiro/tacticalrmm-web` | Vue/Quasar SPA frontend |

---

## Server Requirements

### Minimum Hardware

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 30 GB SSD | 60 GB SSD |
| OS | Ubuntu 22.04 LTS (64-bit) | Ubuntu 22.04 LTS |
| Network | Public static IP | Public static IP |

> **Important:** The server must be a **fresh** Ubuntu 22.04 LTS install.  
> Do not run the installer on a server already running web services — nginx/postgres conflicts will break the install.

### Open Firewall Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 22 | TCP | SSH (restrict to your IP after setup) |
| 80 | TCP | Let's Encrypt certificate validation |
| 443 | TCP | TRMM web UI and API (HTTPS) |
| 4222 | TCP | NATS agent communication |
| 8883 | TCP | NATS agent communication (TLS) |

---

## DNS Requirements

You need **three A records** pointing to your server's public IP before running the installer.  The installer validates DNS before proceeding.

| Subdomain | Example | Purpose |
|-----------|---------|---------|
| `rmm` | `rmm.yourdomain.com` | Web UI |
| `api` | `api.yourdomain.com` | REST API |
| `mesh` | `mesh.yourdomain.com` | MeshCentral |

All three must resolve to the **same IP** as your server.  Allow up to 5 minutes for DNS propagation before installing.

```bash
# Verify all three resolve before starting:
dig +short rmm.yourdomain.com
dig +short api.yourdomain.com
dig +short mesh.yourdomain.com
```

---

## Fresh Install — New Server

### Step 1 — Provision & Prepare the Server

SSH to your server as **root** (or a user with passwordless sudo).

```bash
# Update the system
apt update && apt upgrade -y

# Install git (needed to clone the fork later)
apt install -y git curl wget

# Set a hostname that matches your RMM subdomain (optional but recommended)
hostnamectl set-hostname rmm.yourdomain.com
```

### Step 2 — Run the Official TRMM Installer

We use the upstream installer to set up all infrastructure (nginx, postgres, redis, NATS, MeshCentral, SSL certs, systemd services).  This is the most reliable way to get a working base.

```bash
cd ~
wget -q 'https://raw.githubusercontent.com/amidaware/tacticalrmm/develop/install.sh'
chmod +x install.sh
./install.sh
```

The installer will prompt you for:
- Your three subdomains (`rmm.`, `api.`, `mesh.`)
- A Let's Encrypt email address
- A MeshCentral admin username and password
- A TRMM superuser username, password, and email

The installer takes 10–20 minutes.  When it finishes, **do not log out** — continue with the steps below.

> **Note:** The installer puts the stock `amidaware/tacticalrmm` code at `/rmm`.  We are about to replace it with this fork.

### Step 3 — Swap Backend to This Fork

```bash
cd /rmm

# Stop all TRMM services
systemctl stop rmm celery celerybeat

# Add this fork as a remote and fetch it
git remote add broshiro https://github.com/Broshiro/tacticalrmm.git
git fetch broshiro

# Check out the fork's develop branch, keeping your local config files
git checkout --track broshiro/develop
```

> **Config files** (`.env`, `local_settings.py`) live inside the repo directory but are in `.gitignore` — they will **not** be overwritten by the checkout.

### Step 4 — Install Fork Dependencies

Some fork features require additional Python packages that are not in the upstream requirements.

```bash
cd /rmm
source venv/bin/activate

pip install requests  # already present in most TRMM installs, ensures it's there

# Install all requirements (safe to re-run)
pip install -r api/tacticalrmm/requirements.txt

deactivate
```

### Step 5 — Run Fork Migrations

```bash
cd /rmm/api/tacticalrmm
source /rmm/venv/bin/activate

python manage.py migrate --run-syncdb

deactivate
```

Expected output: a list of migrations applied, ending with `Running deferred SQL... OK`.

### Step 6 — Build and Deploy the Custom Frontend

The frontend must be built from source because TRMM's release tarballs come from `amidaware/tacticalrmm-web`, not this fork.

#### 6a — Install Node.js 20

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node --version  # should print v20.x.x
npm --version
```

#### 6b — Install Quasar CLI

```bash
npm install -g @quasar/cli
```

#### 6c — Clone and Build the Frontend

```bash
cd ~
git clone https://github.com/Broshiro/tacticalrmm-web.git
cd tacticalrmm-web
git checkout develop

# Install Node dependencies
npm install

# Build the production SPA
quasar build
# Output is in: ~/tacticalrmm-web/dist/spa/
```

Build time is typically 2–4 minutes.

#### 6d — Deploy to nginx

```bash
# Back up the current frontend (built from the installer)
cp -r /var/www/rmm/dist /var/www/rmm/dist.stock.bak

# Deploy the new build
rm -rf /var/www/rmm/dist/*
cp -r ~/tacticalrmm-web/dist/spa/. /var/www/rmm/dist/

# Fix ownership
chown -R www-data:www-data /var/www/rmm/dist/
```

### Step 7 — Restart Services

```bash
systemctl daemon-reload
systemctl start rmm celery celerybeat
systemctl reload nginx

# Verify everything is running
systemctl status rmm celery celerybeat nginx meshcentral
```

All five services should show `active (running)`.

**Open your browser to `https://rmm.yourdomain.com` — you should see the Broshiro RMM login page.**

---

## Migrating an Existing TRMM Server

If you already have a working stock TacticalRMM server:

```bash
# 1. SSH to the server as root/sudo user

# 2. Take a full backup first
/rmm/backup.sh

# 3. Stop services
systemctl stop rmm celery celerybeat

# 4. Swap backend (same as Step 3 above)
cd /rmm
git remote add broshiro https://github.com/Broshiro/tacticalrmm.git
git fetch broshiro
git checkout --track broshiro/develop

# 5. Install deps & migrate (same as Steps 4–5 above)
source venv/bin/activate
pip install -r api/tacticalrmm/requirements.txt
python manage.py migrate --run-syncdb
deactivate

# 6. Build and deploy frontend (same as Step 6 above)
# ... (see Step 6)

# 7. Restart
systemctl start rmm celery celerybeat
systemctl reload nginx
```

> **Rollback:** If something goes wrong, restore the frontend backup (`cp -r /var/www/rmm/dist.stock.bak/. /var/www/rmm/dist/`) and point the git remote back to `amidaware/tacticalrmm`.

---

## Vaultwarden Integration Setup

The credential panel in remote sessions pulls login items from your Vaultwarden instance and displays them filtered to the agent's client.  Credentials are fetched server-side — the Vaultwarden master secret is **never sent to the browser**.

### Prerequisites

- A running [Vaultwarden](https://github.com/dani-garcia/vaultwarden) instance reachable from the TRMM server
- A Vaultwarden account (personal or organisation) that contains your client credentials

### Create an API Key in Vaultwarden

1. Log in to your Vaultwarden web vault.
2. Go to **Account Settings → Security → Keys**.
3. Scroll to **API Key** and click **View API Key**.
4. Re-enter your master password when prompted.
5. Note the **`client_id`** (looks like `user.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) and **`client_secret`**.

> **Tip:** If you manage multiple clients, create a dedicated Vaultwarden user with access to all client credential collections rather than using your personal account.

### Configure Environment Variables

The TRMM backend reads Vaultwarden credentials from environment variables so they are never stored in the database.

#### Docker / docker-compose deployments

Add the following to your `.env` file (in `/rmm/` or wherever `docker-compose.yml` lives):

```env
# Vaultwarden integration
VAULTWARDEN_URL=https://vault.yourdomain.com
VAULTWARDEN_CLIENT_ID=user.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
VAULTWARDEN_CLIENT_SECRET=your_client_secret_here
```

Then restart the backend:

```bash
docker-compose restart rmm celery celerybeat
```

#### Bare-metal / systemd deployments

Edit the TRMM backend systemd service override:

```bash
mkdir -p /etc/systemd/system/rmm.service.d/
cat > /etc/systemd/system/rmm.service.d/vaultwarden.conf << 'EOF'
[Service]
Environment="VAULTWARDEN_URL=https://vault.yourdomain.com"
Environment="VAULTWARDEN_CLIENT_ID=user.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
Environment="VAULTWARDEN_CLIENT_SECRET=your_client_secret_here"
EOF

# Same for Celery (if Celery tasks ever need Vault access)
cp /etc/systemd/system/rmm.service.d/vaultwarden.conf \
   /etc/systemd/system/celery.service.d/vaultwarden.conf

systemctl daemon-reload
systemctl restart rmm celery
```

### Organising Credentials by Client

The credential panel filters Vaultwarden items by checking whether the **client's name** (as it appears in TRMM) appears anywhere in the **Vaultwarden item name**.

**Naming convention (recommended):**

```
Acme Corp - Router Admin
Acme Corp - Windows Domain Admin
Acme Corp - Office 365
Smith & Sons - Firewall
Smith & Sons - Server Local Admin
```

When a technician opens Take Control on any agent belonging to client `Acme Corp`, the credential panel will show the first three items and nothing else.

> Matching is case-insensitive.  Symbols in client names (like `&`) must also appear in the Vaultwarden item name for a match.

---

## Remote Session Features

All three features are available in the **Take Control** toolbar at the top of the remote session window.

### Clipboard Sync

Clicks the **Sync Clipboard** button to copy your local clipboard to the remote machine.

1. Copy text on your local machine (Ctrl+C as usual).
2. Open Take Control on the target agent.
3. Click **Sync Clipboard** in the top toolbar.
4. The text is now in the remote machine's clipboard — press Ctrl+V inside the remote session to paste.

> **Browser permission:** On first use, Chrome/Edge will ask for clipboard-read permission.  Click **Allow**.  Firefox may require enabling `dom.events.asyncClipboard.readText` in `about:config`.

### Send as Keystrokes

Injects text directly into the remote session without using the clipboard.

1. Click **Send Keys** in the toolbar.
2. Type or paste the text you want to send.
3. Press **Send to Remote** (or Ctrl+Enter).
4. The text is pushed to the remote clipboard and a paste command is triggered automatically.

If the auto-paste doesn't fire (depends on MeshCentral version), you will see a notification:  
*"Text set on remote clipboard — Ctrl+V to paste"* — simply click in the remote window and press Ctrl+V.

### Credential Panel

A slide-in sidebar that shows Vaultwarden credentials for the agent's client.

1. Click **Credentials** in the toolbar.  The panel slides in from the right; the remote desktop shrinks to accommodate it.
2. Use the search box to filter credentials by name or username.
3. Expand any credential to reveal its fields:
   - **Copy icon** — copies the value to your local clipboard.
   - **Keyboard icon** — sends the value directly to the remote machine as keystrokes.
   - **Eye icon** — reveals/hides the password.
4. Click **Credentials** again (or the × in the panel) to close it and restore full-width remote desktop.

---

## Environment Variable Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `VAULTWARDEN_URL` | No | Base URL of your Vaultwarden instance, e.g. `https://vault.example.com` |
| `VAULTWARDEN_CLIENT_ID` | No | Vaultwarden personal API key `client_id` |
| `VAULTWARDEN_CLIENT_SECRET` | No | Vaultwarden personal API key `client_secret` |

All upstream TRMM environment variables (database URL, secret key, mesh settings, etc.) are unchanged.  See [docs.tacticalrmm.com](https://docs.tacticalrmm.com) for those.

If none of the three Vaultwarden variables are set, the credential panel loads an empty list and does not contact any external service.

---

## Updating the Fork

To pull the latest commits from this fork:

```bash
# Backend
cd /rmm
systemctl stop rmm celery celerybeat
git pull broshiro develop
source venv/bin/activate
pip install -r api/tacticalrmm/requirements.txt
python manage.py migrate
deactivate
systemctl start rmm celery celerybeat

# Frontend — rebuild and redeploy
cd ~/tacticalrmm-web
git pull origin develop
npm install
quasar build
rm -rf /var/www/rmm/dist/*
cp -r dist/spa/. /var/www/rmm/dist/
chown -R www-data:www-data /var/www/rmm/dist/
systemctl reload nginx
```

---

## Pulling Upstream Changes

To merge new features and bug fixes from `amidaware/tacticalrmm` into this fork:

```bash
# Backend
cd /rmm
git remote add upstream https://github.com/amidaware/tacticalrmm.git
git fetch upstream
git checkout develop
git merge upstream/develop
# Resolve any conflicts, then push:
git push broshiro develop

# Frontend
cd ~/tacticalrmm-web
git remote add upstream https://github.com/amidaware/tacticalrmm-web.git
git fetch upstream
git checkout develop
git merge upstream/develop
git push origin develop
```

After merging, always re-run migrations and rebuild the frontend.

---

## Planned Features & Roadmap

See the [GitHub Issues](https://github.com/Broshiro/tacticalrmm/issues) for full specifications.  High-level roadmap:

### Next Up
- **#10** Remove overdue checkmarks — cleaner agent list UI
- **#11** Optional sites — create clients without requiring a site first

### Short Term
- **#13** Automation engine — trigger scripts on a schedule with scope filtering (all agents, per-client, per-site, per-device-type, per-OS)
- **#14** Email & SMS alerts — extend upstream alerting with custom templates
- **#17** Agent custom fields — define fields collected by scripts (e.g. storage type, gateway info)

### Medium Term
- **#15** Zammad ticketing integration — auto-create/close tickets from alerts
- **#16** Patch compliance reporting — per-client patch status dashboard
- **#18** Onboarding profiles — auto-install software when a new agent checks in

---

## Development Setup

### Backend (local)

```bash
git clone https://github.com/Broshiro/tacticalrmm.git
cd tacticalrmm
python3 -m venv venv
source venv/bin/activate
pip install -r api/tacticalrmm/requirements.txt
pip install -r api/tacticalrmm/requirements-dev.txt

# Copy and edit local settings
cp api/tacticalrmm/local_settings.example.py api/tacticalrmm/local_settings.py
# Edit local_settings.py with your DB and Redis credentials

cd api/tacticalrmm
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Frontend (local)

```bash
git clone https://github.com/Broshiro/tacticalrmm-web.git
cd tacticalrmm-web
npm install

# Create local environment file and set API base URL
cp .env.example .env
# Edit .env: VITE_APP_API=http://localhost:8000

quasar dev   # starts dev server at http://localhost:9000
```

### Branch Naming

| Prefix | Purpose |
|--------|---------|
| `feature/` | New feature (references an issue number) |
| `fix/` | Bug fix |
| `chore/` | Dependency bumps, CI, config |
| `docs/` | Documentation only |

---

## Contributing

1. **Fork** this repo to your own GitHub account.
2. Create a branch: `git checkout -b feature/my-feature`
3. Make your changes, write tests where applicable.
4. Push to your fork and open a **Pull Request** targeting `Broshiro/tacticalrmm:develop`.
5. Reference the relevant GitHub issue in your PR description.

**Before submitting:**
- Run `black api/` to format Python code.
- Run `npm run lint` in the frontend repo.
- Ensure no new migrations are missing (`python manage.py makemigrations --check`).

---

## License

This project inherits the license from the upstream TacticalRMM project.  
See [LICENSE](./LICENSE) for details.

This is an independent fork and is **not** affiliated with or endorsed by Amidaware Inc.
