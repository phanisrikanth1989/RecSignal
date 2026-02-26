# RecSignal — UAT Deployment Guide (Non-Docker / Unix Server)

**Document Version:** 1.0  
**Date:** February 2026  
**Environment:** UAT  
**Prepared for:** Step-by-step manual deployment on a Unix/Linux server

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Pre-Deployment Checklist](#2-pre-deployment-checklist)
3. [Server & Network Requirements](#3-server--network-requirements)
4. [Step 1 — Prepare the UAT App Server](#step-1--prepare-the-uat-app-server)
5. [Step 2 — Copy Source Code to Server](#step-2--copy-source-code-to-server)
6. [Step 3 — Deploy the Backend (FastAPI)](#step-3--deploy-the-backend-fastapi)
7. [Step 4 — Build and Deploy the Frontend (React)](#step-4--build-and-deploy-the-frontend-react)
8. [Step 5 — Configure Nginx as Reverse Proxy](#step-5--configure-nginx-as-reverse-proxy)
9. [Step 6 — Run First-Time Database Setup](#step-6--run-first-time-database-setup)
10. [Step 7 — Deploy Unix Monitoring Agents](#step-7--deploy-unix-monitoring-agents)
11. [Step 8 — Deploy Oracle Monitoring Agent](#step-8--deploy-oracle-monitoring-agent)
12. [Step 9 — Verify Everything is Working](#step-9--verify-everything-is-working)
13. [Step 10 — Ongoing Operations](#step-10--ongoing-operations)
14. [Troubleshooting](#troubleshooting)

---

## 1. Architecture Overview

```
                          ┌────────────────────────────────────────┐
                          │         UAT App Server                 │
    Browser ─────────────►│  Nginx (port 80)                       │
                          │   ├── /         → React static files   │
                          │   └── /api/     → FastAPI (port 8000)  │
                          │                                        │
                          │  FastAPI Backend (systemd service)     │
                          │   └── connects to Oracle UAT DB        │
                          └──────────────────┬─────────────────────┘
                                             │
              ┌──────────────────────────────┴─────────────────────────┐
              │                                                         │
   ┌──────────▼──────────┐                              ┌──────────────▼──────────┐
   │  UAT Unix Servers   │                              │  Oracle UAT Database    │
   │  (lswtlmap1u, etc.) │                              │  (uat-ora-01)           │
   │  unix_agent.py      │                              │  oracle_agent.py        │
   │  (cron every 5 min) │                              │  (cron every 5 min)     │
   └─────────────────────┘                              └─────────────────────────┘
```

### Components Being Deployed

| Component | Location | Purpose |
|-----------|----------|---------|
| **RecSignal Frontend** | UAT App Server | React UI served via Nginx |
| **RecSignal Backend** | UAT App Server | FastAPI REST API (Python) |
| **unix_agent.py** | Each monitored Unix server | Ships CPU/memory/disk metrics |
| **oracle_agent.py** | Any host with Oracle DB access | Ships Oracle DB health metrics |

---

## 2. Pre-Deployment Checklist

Gather the following information **before you begin**. Fill in the blanks.

| # | Item | Your Value |
|---|------|------------|
| 1 | UAT App Server hostname/IP | `___________________` |
| 2 | Oracle UAT DB host | `___________________` |
| 3 | Oracle UAT DB port | `1521` (or `___________`) |
| 4 | Oracle UAT DB service name | `___________________` |
| 5 | Oracle monitoring username | `___________________` |
| 6 | Oracle monitoring password | `___________________` |
| 7 | List of Unix servers to monitor | `lswtlmap1u, lswtlmap2u, lswtlmap3u, sd-20d3-4317` |
| 8 | SSH access to UAT App Server | Confirm: Yes / No |
| 9 | SSH access to each Unix server | Confirm: Yes / No |
| 10 | Sudo/root access on UAT App Server | Confirm: Yes / No |

---

## 3. Server & Network Requirements

### UAT App Server Minimum Specs
- OS: RHEL 7+, Ubuntu 18.04+, or equivalent Unix
- RAM: 2 GB minimum (4 GB recommended)
- CPU: 2 cores minimum
- Disk: 10 GB free
- Python: 3.11 or later
- Node.js: 18 or later *(only needed to build the frontend)*
- Nginx: 1.18 or later

### Firewall / Network Ports to Open

| From | To | Port | Purpose |
|------|----|------|---------|
| Browser / Users | UAT App Server | **80** | Access the RecSignal UI |
| UAT App Server | Oracle UAT DB | **1521** | Backend connects to Oracle |
| Unix Servers (agents) | UAT App Server | **80** | Agents POST metrics to backend |
| Oracle-accessible host | UAT App Server | **80** | Oracle agent POSTs metrics |

> **Note:** Port 8000 (FastAPI) does NOT need to be open externally. Nginx proxies it internally.

### Oracle DB Access Required
The Oracle monitoring user needs **read-only SELECT** on the following views:
```sql
GRANT SELECT ON V_$SESSION        TO monitor_user;
GRANT SELECT ON V_$TABLESPACE     TO monitor_user;
GRANT SELECT ON DBA_TABLESPACES   TO monitor_user;
GRANT SELECT ON DBA_DATA_FILES    TO monitor_user;
GRANT SELECT ON V_$SYSSTAT        TO monitor_user;
GRANT SELECT ON V_$OSSTAT         TO monitor_user;
GRANT SELECT ON V_$DATABASE       TO monitor_user;
GRANT SELECT ON V_$INSTANCE       TO monitor_user;
```

---

## Step 1 — Prepare the UAT App Server

SSH into the UAT App Server and run all commands below as a user with sudo access.

### 1.1 Update the system

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# RHEL/CentOS
sudo yum update -y
```

### 1.2 Install Python 3.11

```bash
# Ubuntu 22.04+
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# RHEL/CentOS 8+
sudo dnf install -y python3.11 python3.11-devel
```

Verify:
```bash
python3.11 --version
# Expected: Python 3.11.x
```

### 1.3 Install Node.js 18 (needed only to build the frontend)

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# RHEL/CentOS
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo yum install -y nodejs
```

Verify:
```bash
node --version    # Expected: v18.x.x
npm --version     # Expected: 9.x.x or 10.x.x
```

### 1.4 Install Nginx

```bash
# Ubuntu/Debian
sudo apt install -y nginx

# RHEL/CentOS
sudo yum install -y nginx
```

Verify:
```bash
nginx -v
# Expected: nginx version: nginx/1.x.x
```

### 1.5 Create the application directory structure

```bash
sudo mkdir -p /opt/recsignal/backend
sudo mkdir -p /opt/recsignal/frontend
sudo mkdir -p /var/www/recsignal
sudo mkdir -p /var/log/recsignal

# Create a dedicated service user (optional but recommended)
sudo useradd -r -s /bin/false recsignal

# Set ownership
sudo chown -R recsignal:recsignal /opt/recsignal
sudo chown -R recsignal:recsignal /var/log/recsignal
sudo chown -R nginx:nginx /var/www/recsignal   # or www-data on Ubuntu
```

---

## Step 2 — Copy Source Code to Server

### Option A — Using Git (Recommended)

```bash
cd /opt/recsignal

# Clone the repository
sudo -u recsignal git clone https://github.com/YOUR_ORG/RecSignal.git .
# OR if you have an internal repo:
sudo -u recsignal git clone git@your-internal-git:RecSignal.git .
```

### Option B — Using SCP from your local machine

Run these commands **from your local Windows machine** (Git Bash or PowerShell):

```bash
# Copy backend
scp -r C:/Users/phani/OneDrive/Documents/GitHub/RecSignal/backend/* user@<uat-server>:/opt/recsignal/backend/

# Copy frontend
scp -r C:/Users/phani/OneDrive/Documents/GitHub/RecSignal/frontend/* user@<uat-server>:/opt/recsignal/frontend/

# Copy agents
scp -r C:/Users/phani/OneDrive/Documents/GitHub/RecSignal/agents/* user@<uat-server>:/opt/recsignal/agents/
```

### Option C — Using rsync

```bash
rsync -avz --progress \
  /mnt/c/Users/phani/OneDrive/Documents/GitHub/RecSignal/ \
  user@<uat-server>:/opt/recsignal/
```

### Verify files are in place

```bash
ls /opt/recsignal/backend/     # Should show: app/ requirements.txt Dockerfile seed_data.py
ls /opt/recsignal/frontend/    # Should show: src/ public/ package.json
ls /opt/recsignal/agents/      # Should show: unix_agent.py oracle_agent.py requirements.txt
```

---

## Step 3 — Deploy the Backend (FastAPI)

### 3.1 Create the Python virtual environment

```bash
cd /opt/recsignal/backend
python3.11 -m venv venv
source venv/bin/activate

# Verify you are using the right Python
which python
# Expected: /opt/recsignal/backend/venv/bin/python
```

### 3.2 Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs: FastAPI, Uvicorn, oracledb, pydantic, httpx, and others.

### 3.3 Create the environment configuration file

```bash
sudo nano /opt/recsignal/backend/.env
```

Paste the following and fill in your values:

```bash
# ── Database ──────────────────────────────────────────────────────────────
DB_TYPE=oracle
DB_USER=your_oracle_monitor_username
DB_PASSWORD=your_oracle_monitor_password
DB_DSN=your-oracle-host:1521/your_service_name
DB_POOL_MIN=2
DB_POOL_MAX=10

# ── Application ───────────────────────────────────────────────────────────
ENVIRONMENT=UAT
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

Secure the file:
```bash
sudo chmod 600 /opt/recsignal/backend/.env
sudo chown recsignal:recsignal /opt/recsignal/backend/.env
```

### 3.4 Test the backend manually (before setting up service)

```bash
cd /opt/recsignal/backend
source venv/bin/activate

# Load env vars temporarily for testing
export $(cat .env | grep -v '#' | xargs)

# Start manually
uvicorn app.main:app --host 127.0.0.1 --port 8000

# You should see output like:
# INFO:     Started server process [xxxxx]
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

From another terminal session, test it:
```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok"} or similar
```

Press `Ctrl+C` to stop the test run.

### 3.5 Create the systemd service

```bash
sudo nano /etc/systemd/system/recsignal-backend.service
```

Paste this exactly:

```ini
[Unit]
Description=RecSignal FastAPI Backend
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=recsignal
Group=recsignal
WorkingDirectory=/opt/recsignal/backend
EnvironmentFile=/opt/recsignal/backend/.env
ExecStart=/opt/recsignal/backend/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-level info
Restart=always
RestartSec=10
StandardOutput=append:/var/log/recsignal/backend.log
StandardError=append:/var/log/recsignal/backend.log

[Install]
WantedBy=multi-user.target
```

### 3.6 Enable and start the backend service

```bash
sudo systemctl daemon-reload
sudo systemctl enable recsignal-backend
sudo systemctl start recsignal-backend

# Check status — should say "active (running)"
sudo systemctl status recsignal-backend
```

Expected output:
```
● recsignal-backend.service - RecSignal FastAPI Backend
   Loaded: loaded (/etc/systemd/system/recsignal-backend.service; enabled)
   Active: active (running) since ...
```

Check the logs:
```bash
tail -f /var/log/recsignal/backend.log
```

---

## Step 4 — Build and Deploy the Frontend (React)

### 4.1 Install Node dependencies

```bash
cd /opt/recsignal/frontend
npm install
```

This may take 2–5 minutes. It downloads all React packages.

### 4.2 Set the API URL and build

The React app needs to know the backend URL **at build time**.

```bash
# Replace <uat-server-hostname-or-ip> with your actual server address
REACT_APP_API_URL=http://<uat-server-hostname-or-ip> npm run build
```

Example:
```bash
REACT_APP_API_URL=http://uat-recsignal.yourcompany.com npm run build
# OR using IP:
REACT_APP_API_URL=http://192.168.1.100 npm run build
```

This creates a `build/` folder with optimised static files.

### 4.3 Copy the build output to Nginx web root

```bash
sudo cp -r /opt/recsignal/frontend/build/* /var/www/recsignal/

# Set correct permissions
sudo chown -R nginx:nginx /var/www/recsignal    # RHEL
# OR
sudo chown -R www-data:www-data /var/www/recsignal  # Ubuntu
```

Verify files are there:
```bash
ls /var/www/recsignal/
# Expected: index.html  static/  asset-manifest.json  favicon.ico  ...
```

---

## Step 5 — Configure Nginx as Reverse Proxy

### 5.1 Create the RecSignal Nginx config

```bash
sudo nano /etc/nginx/conf.d/recsignal.conf
```

Paste the following:

```nginx
server {
    listen 80;
    server_name <uat-server-hostname-or-ip>;   # Replace with your UAT server address

    root /var/www/recsignal;
    index index.html;

    # ── Frontend: React Router (serve index.html for all UI routes) ───────
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ── Backend: Proxy all /api/ calls to FastAPI ─────────────────────────
    location /api/ {
        proxy_pass         http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # ── Static asset caching ──────────────────────────────────────────────
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Access and error logs
    access_log /var/log/nginx/recsignal-access.log;
    error_log  /var/log/nginx/recsignal-error.log;
}
```

### 5.2 Disable the default Nginx site (to avoid conflicts)

```bash
# Ubuntu/Debian
sudo rm -f /etc/nginx/sites-enabled/default

# RHEL — rename or remove default.conf
sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak
```

### 5.3 Test and reload Nginx

```bash
# Test the config for syntax errors
sudo nginx -t

# Expected:
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful

# Reload Nginx
sudo systemctl enable nginx
sudo systemctl reload nginx
```

### 5.4 Verify the app is accessible

From your browser, open:
```
http://<uat-server-hostname-or-ip>
```

You should see the RecSignal login/dashboard page.

---

## Step 6 — Run First-Time Database Setup

The backend automatically creates the Oracle schema tables on first startup. Verify this happened:

```bash
# Check backend logs for schema creation messages
grep -i "DDL\|CREATE\|schema\|bootstrap" /var/log/recsignal/backend.log
```

You should see lines like:
```
INFO | app.main | Schema bootstrap complete.
```

### 6.1 Verify Oracle connection

```bash
curl http://127.0.0.1:8000/servers
# Expected: [] or a JSON array of servers (not a 500 error)
```

### 6.2 (Optional) Register UAT servers manually

If you want the UAT servers pre-registered in the database, POST them via the API:

```bash
curl -X POST http://127.0.0.1:8000/servers \
  -H "Content-Type: application/json" \
  -d '{"hostname": "lswtlmap1u", "environment": "UAT", "server_type": "UNIX"}'

curl -X POST http://127.0.0.1:8000/servers \
  -H "Content-Type: application/json" \
  -d '{"hostname": "lswtlmap2u", "environment": "UAT", "server_type": "UNIX"}'

curl -X POST http://127.0.0.1:8000/servers \
  -H "Content-Type: application/json" \
  -d '{"hostname": "lswtlmap3u", "environment": "UAT", "server_type": "UNIX"}'

curl -X POST http://127.0.0.1:8000/servers \
  -H "Content-Type: application/json" \
  -d '{"hostname": "sd-20d3-4317", "environment": "UAT", "server_type": "UNIX"}'

curl -X POST http://127.0.0.1:8000/servers \
  -H "Content-Type: application/json" \
  -d '{"hostname": "uat-ora-01.internal", "environment": "UAT", "server_type": "ORACLE"}'
```

> Servers are also auto-registered the first time an agent sends metrics for them.

---

## Step 7 — Deploy Unix Monitoring Agents

Repeat the following steps on **each Unix server you want to monitor**  
(e.g., `lswtlmap1u`, `lswtlmap2u`, `lswtlmap3u`, `sd-20d3-4317`).

SSH into the Unix server first:
```bash
ssh user@lswtlmap1u
```

### 7.1 Install Python and pip (if not present)

```bash
python3 --version   # Check if Python 3.8+ is already installed

# If not, install:
sudo yum install -y python3 python3-pip   # RHEL
# OR
sudo apt install -y python3 python3-pip   # Ubuntu
```

### 7.2 Create agent directory

```bash
sudo mkdir -p /opt/recsignal
sudo chown $USER:$USER /opt/recsignal
```

### 7.3 Copy the agent script

From the UAT App Server (or from your local machine):

```bash
# From UAT App Server:
scp /opt/recsignal/agents/unix_agent.py user@lswtlmap1u:/opt/recsignal/

# OR from local machine:
scp C:/Users/phani/OneDrive/Documents/GitHub/RecSignal/agents/unix_agent.py user@lswtlmap1u:/opt/recsignal/
```

### 7.4 Install agent dependencies

```bash
pip3 install requests
# OR if pip3 is not in PATH:
python3 -m pip install requests
```

### 7.5 Test the agent manually

```bash
export RECSIGNAL_API_URL=http://<uat-app-server-ip>
export RECSIGNAL_ENV=UAT

python3 /opt/recsignal/unix_agent.py
```

Expected output:
```
2026-02-26 10:00:01 | INFO     | unix_agent | Collected metrics for lswtlmap1u
2026-02-26 10:00:01 | INFO     | unix_agent | Posted metrics successfully (200)
```

### 7.6 Set up cron job (runs every 5 minutes)

```bash
crontab -e
```

Add the following line:

```cron
*/5 * * * * RECSIGNAL_API_URL=http://<uat-app-server-ip> RECSIGNAL_ENV=UAT /usr/bin/python3 /opt/recsignal/unix_agent.py >> /var/log/recsignal-agent.log 2>&1
```

Verify the cron is saved:
```bash
crontab -l
```

Create the log file:
```bash
sudo touch /var/log/recsignal-agent.log
sudo chmod 666 /var/log/recsignal-agent.log
```

**Repeat Steps 7.1 – 7.6 on every Unix server to be monitored.**

---

## Step 8 — Deploy Oracle Monitoring Agent

This agent can run on **any server that has network connectivity to your Oracle UAT database** — it could be the UAT App Server itself, or a dedicated monitoring host.

### 8.1 Create agent directory (if not already done)

```bash
sudo mkdir -p /opt/recsignal
sudo chown $USER:$USER /opt/recsignal
```

### 8.2 Copy the Oracle agent script

```bash
cp /opt/recsignal/agents/oracle_agent.py /opt/recsignal/oracle_agent.py
```

### 8.3 Install agent dependencies

```bash
pip3 install oracledb requests
# OR
python3 -m pip install oracledb requests
```

### 8.4 Create the Oracle agent environment file

```bash
nano /opt/recsignal/oracle_agent.env
```

Paste and fill in your values:

```bash
ORA_USER=your_oracle_monitor_username
ORA_PASSWORD=your_oracle_monitor_password
ORA_DSN=your-oracle-host:1521/your_service_name
ORA_HOSTNAME=uat-ora-01
RECSIGNAL_API_URL=http://<uat-app-server-ip>
RECSIGNAL_ENV=UAT
```

Secure the file:
```bash
chmod 600 /opt/recsignal/oracle_agent.env
```

### 8.5 Test the Oracle agent manually

```bash
export $(cat /opt/recsignal/oracle_agent.env | grep -v '#' | xargs)

python3 /opt/recsignal/oracle_agent.py
```

Expected output:
```
2026-02-26 10:00:01 | INFO     | oracle_agent | Connected to Oracle: uat-ora-01
2026-02-26 10:00:02 | INFO     | oracle_agent | Collected tablespace metrics
2026-02-26 10:00:02 | INFO     | oracle_agent | Posted metrics successfully (200)
```

### 8.6 Set up cron job (runs every 5 minutes)

```bash
crontab -e
```

Add:

```cron
*/5 * * * * source /opt/recsignal/oracle_agent.env && /usr/bin/python3 /opt/recsignal/oracle_agent.py >> /var/log/recsignal-oracle-agent.log 2>&1
```

Or alternatively using the env command:
```cron
*/5 * * * * /usr/bin/env $(cat /opt/recsignal/oracle_agent.env | grep -v '#' | xargs) /usr/bin/python3 /opt/recsignal/oracle_agent.py >> /var/log/recsignal-oracle-agent.log 2>&1
```

Create the log file:
```bash
sudo touch /var/log/recsignal-oracle-agent.log
sudo chmod 666 /var/log/recsignal-oracle-agent.log
```

---

## Step 9 — Verify Everything is Working

### 9.1 Service health checks

On the UAT App Server:

```bash
# Backend service running?
sudo systemctl status recsignal-backend
# Expected: active (running)

# Nginx running?
sudo systemctl status nginx
# Expected: active (running)
```

### 9.2 API health check

```bash
curl http://127.0.0.1:8000/servers
# Expected: JSON array (not an error)

curl http://127.0.0.1:8000/alerts
# Expected: JSON array
```

### 9.3 Frontend accessible

Open in browser:
```
http://<uat-app-server-hostname-or-ip>
```

You should see the RecSignal dashboard.

### 9.4 Verify agent data is flowing

After 5–10 minutes (one cron run), check:

```bash
# API should now show servers
curl http://127.0.0.1:8000/servers | python3 -m json.tool

# Check metrics exist
curl http://127.0.0.1:8000/metrics | python3 -m json.tool
```

### 9.5 Check agent logs

On each Unix server:
```bash
tail -50 /var/log/recsignal-agent.log
# Should show: "Posted metrics successfully (200)"
```

On Oracle agent host:
```bash
tail -50 /var/log/recsignal-oracle-agent.log
# Should show: "Posted metrics successfully (200)"
```

---

## Step 10 — Ongoing Operations

### Start / Stop / Restart the backend

```bash
sudo systemctl start   recsignal-backend
sudo systemctl stop    recsignal-backend
sudo systemctl restart recsignal-backend
sudo systemctl status  recsignal-backend
```

### View backend logs

```bash
# Live tail
tail -f /var/log/recsignal/backend.log

# Last 100 lines
tail -100 /var/log/recsignal/backend.log

# Via journalctl
sudo journalctl -u recsignal-backend -f
```

### Deploy a code update

When new code is available:

```bash
# 1. Pull/copy new backend code
cd /opt/recsignal/backend
git pull   # or scp new files

# 2. Activate venv and update dependencies if requirements.txt changed
source venv/bin/activate
pip install -r requirements.txt

# 3. Restart backend
sudo systemctl restart recsignal-backend

# 4. If frontend changed, rebuild and redeploy:
cd /opt/recsignal/frontend
git pull   # or scp updated src/
REACT_APP_API_URL=http://<uat-server> npm run build
sudo cp -r build/* /var/www/recsignal/
sudo systemctl reload nginx
```

### Log rotation

Create a logrotate config to prevent logs from growing indefinitely:

```bash
sudo nano /etc/logrotate.d/recsignal
```

```
/var/log/recsignal/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    copytruncate
}
```

---

## Troubleshooting

### Backend won't start — Oracle connection error

```bash
# Check the log
tail -50 /var/log/recsignal/backend.log

# Common errors:
# ORA-12541: TNS:no listener       → Oracle host/port wrong in .env
# ORA-01017: invalid username      → Wrong DB_USER or DB_PASSWORD
# ORA-12514: TNS:listener does not know of service  → Wrong service name in DB_DSN
```

Fix: Edit `/opt/recsignal/backend/.env` with correct credentials and restart.

---

### Nginx shows 502 Bad Gateway

The backend is not running or not listening.

```bash
sudo systemctl status recsignal-backend
sudo systemctl restart recsignal-backend
curl http://127.0.0.1:8000/servers   # should respond
```

---

### React app loads but API calls fail (CORS or 404)

Ensure the Nginx `location /api/` block is correct and proxying to port 8000.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Also check that `REACT_APP_API_URL` was set correctly **before** running `npm run build`.

---

### Agent reports "Connection refused" or "Failed to POST metrics"

The agent cannot reach the backend. Check:
1. The UAT App Server IP is reachable from the agent server: `ping <uat-app-server-ip>`
2. Port 80 is open: `curl http://<uat-app-server-ip>/api/servers`
3. The `RECSIGNAL_API_URL` in the cron job matches the UAT server address.

---

### Python `oracledb` cannot find Oracle client libraries

`oracledb` in **thin mode** (default) does **not** require Oracle client libraries installed on the machine — it connects natively. If you see `DPI-1047`, force thin mode by ensuring you are using `oracledb >= 1.0` with no `init_oracle_client()` call.

---

## Summary: Quick Reference

| What | Command |
|------|---------|
| Start backend | `sudo systemctl start recsignal-backend` |
| Stop backend | `sudo systemctl stop recsignal-backend` |
| Backend logs | `tail -f /var/log/recsignal/backend.log` |
| Check all services | `sudo systemctl status recsignal-backend nginx` |
| Test API | `curl http://127.0.0.1:8000/servers` |
| Rebuild frontend | `cd /opt/recsignal/frontend && REACT_APP_API_URL=http://<server> npm run build && sudo cp -r build/* /var/www/recsignal/` |
| Check agent logs | `tail -f /var/log/recsignal-agent.log` |
| Open in browser | `http://<uat-server-ip>` |
