# RecSignal — Internal DevOps Monitoring Platform

> Centralised monitoring and alerting for Unix servers and Oracle databases across DEV, UAT and PROD environments.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RecSignal Platform                        │
│                                                                  │
│  ┌──────────────┐    HTTP POST     ┌──────────────────────────┐ │
│  │  Unix Agent  │ ──────────────▶  │   FastAPI Backend         │ │
│  │ (cron / 5m)  │                  │                           │ │
│  └──────────────┘                  │  /metrics/ingest          │ │
│                                    │  /servers                 │ │
│  ┌──────────────┐    HTTP POST     │  /alerts                  │ │
│  │ Oracle Agent │ ──────────────▶  │  /config                  │ │
│  │ (cron / 5m)  │                  │  /dashboard               │ │
│  └──────────────┘                  └──────────┬───────────────┘ │
│                                               │ Oracle DB        │
│  ┌──────────────────────────────┐             ▼                  │
│  │    React Frontend            │  ┌─────────────────────────┐  │
│  │                              │  │  Oracle XE              │  │
│  │  Dashboard / Alerts / Config │  │  servers                │  │
│  │  Recharts trend graphs       │  │  metrics                │  │
│  │  Axios → FastAPI REST        │  │  alerts                 │  │
│  └──────────────────────────────┘  │  config                 │  │
│                                    └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
recsignal/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry + lifespan + /dashboard
│   │   ├── models.py            # Pydantic schemas + Oracle DDL
│   │   ├── database.py          # Connection pool + dependency injection
│   │   ├── routes/
│   │   │   ├── servers.py       # GET /servers, POST /servers
│   │   │   ├── metrics.py       # POST /metrics/ingest, GET /metrics
│   │   │   ├── alerts.py        # GET/POST /alerts
│   │   │   └── config.py        # GET/POST /config
│   │   └── services/
│   │       ├── alert_engine.py  # Threshold evaluation + deduplication
│   │       ├── unix_monitor.py  # Disk / CPU / memory collectors (utility)
│   │       └── oracle_monitor.py# Tablespace / blocking / long-query collectors
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.js               # Router + navigation
│   │   ├── App.css              # Global dark-mode styles
│   │   ├── index.js
│   │   ├── api/
│   │   │   └── api.js           # Axios client + all API calls
│   │   ├── pages/
│   │   │   ├── Dashboard.js     # Live overview
│   │   │   ├── Alerts.js        # Alert management
│   │   │   └── Config.js        # Threshold editor
│   │   └── components/
│   │       ├── ServerCard.js    # Server summary card
│   │       ├── MetricsChart.js  # Recharts time-series
│   │       └── AlertList.js     # Reusable alert table
│   ├── public/index.html
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
│
├── agents/
│   ├── unix_agent.py            # Unix cron agent
│   └── oracle_agent.py          # Oracle cron agent
│
├── docker-compose.yml
└── README.md
```

---

## Quick Start

### 1. Docker Compose (recommended)

```bash
# Clone and enter the project
cd RecSignal

# Start all services (Oracle XE + Backend + Frontend)
docker-compose up -d --build

# Tail backend logs
docker-compose logs -f recsignal-backend
```

| Service          | URL                        |
|------------------|----------------------------|
| Frontend         | http://localhost:3000       |
| Backend API docs | http://localhost:8000/docs  |
| Oracle DB        | localhost:1521 (XEPDB1)     |

> **Note:** Oracle XE takes ~2 minutes to initialise on first run.

---

### 2. Manual Development Setup

#### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt

# Set environment variables
set DB_USER=recsignal
set DB_PASSWORD=recsignal123
set DB_DSN=localhost:1521/XEPDB1

uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

---

## Agent Deployment

### Unix Agent

Copy `agents/unix_agent.py` to each Unix server and add a cron entry:

```cron
*/5 * * * * python3 /opt/recsignal/unix_agent.py >> /var/log/recsignal-agent.log 2>&1
```

Required environment variables on the server:

| Variable            | Default                          | Description                   |
|---------------------|----------------------------------|-------------------------------|
| `RECSIGNAL_API_URL` | `http://recsignal-backend:8000`  | RecSignal backend URL         |
| `RECSIGNAL_ENV`     | `DEV`                            | DEV / UAT / PROD              |
| `AGENT_HOSTNAME`    | auto-detected FQDN               | Override hostname             |
| `RECSIGNAL_API_KEY` | *(empty)*                        | Bearer token (optional)       |

### Oracle Agent

```bash
pip install oracledb requests

export ORA_USER=monitor_user
export ORA_PASSWORD=secret
export ORA_DSN=ora-prod-host:1521/PRODDB
export RECSIGNAL_API_URL=http://recsignal-backend:8000
export RECSIGNAL_ENV=PROD

python3 /opt/recsignal/oracle_agent.py
```

Required Oracle grants on the monitored DB:

```sql
GRANT SELECT ON dba_data_files  TO monitor_user;
GRANT SELECT ON dba_free_space  TO monitor_user;
GRANT SELECT ON v_$session      TO monitor_user;
GRANT SELECT ON v_$sql          TO monitor_user;
```

---

## REST API Reference

| Method | Endpoint                         | Description                       |
|--------|----------------------------------|-----------------------------------|
| GET    | `/dashboard`                     | Stats + recent alerts             |
| GET    | `/servers/`                      | List servers (filter by env/type) |
| POST   | `/servers/`                      | Register new server               |
| POST   | `/metrics/ingest`                | Bulk metric ingest (agent use)    |
| GET    | `/metrics/`                      | Historical metrics (charts)       |
| GET    | `/metrics/latest`                | Latest reading per metric/label   |
| GET    | `/alerts/`                       | List alerts (filter by status)    |
| POST   | `/alerts/acknowledge`            | Acknowledge an open alert         |
| POST   | `/alerts/{id}/resolve`           | Resolve an alert                  |
| GET    | `/config/`                       | List all threshold configs        |
| POST   | `/config/update`                 | Create or update a threshold      |
| GET    | `/health`                        | Liveness probe                    |

Full interactive docs: **http://localhost:8000/docs**

---

## Database Schema

```sql
servers  (id, hostname, environment, type, active, created_at)
metrics  (id, server_id, metric_type, value, label, timestamp)
alerts   (id, server_id, metric, severity, label, value, message,
          status, acknowledged_by, created_at, resolved_at)
config   (id, metric_type, environment, warning_threshold, critical_threshold)
```

Schema is bootstrapped automatically on first backend startup.

---

## Alert Logic

1. Agent POSTs metrics to `/metrics/ingest`.
2. `AlertEngine` loads thresholds from `config` table.
3. If `value >= critical_threshold` → severity = **CRITICAL**.
4. If `value >= warning_threshold` → severity = **WARNING**.
5. Existing open/acknowledged alerts for the same (server, metric, label) are **suppressed** (deduplication).
6. If value returns to OK, open alerts are **auto-resolved**.

---

## Environment Variables

| Variable         | Service  | Default              | Description             |
|------------------|----------|----------------------|-------------------------|
| `DB_USER`        | backend  | `recsignal`          | Oracle username         |
| `DB_PASSWORD`    | backend  | `recsignal123`       | Oracle password         |
| `DB_DSN`         | backend  | `localhost:1521/XEPDB1` | Oracle DSN           |
| `DB_POOL_MIN`    | backend  | `2`                  | Connection pool min     |
| `DB_POOL_MAX`    | backend  | `10`                 | Connection pool max     |
| `REACT_APP_API_URL` | frontend | `http://localhost:8000` | Backend base URL  |

---

## Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Backend   | Python 3.11, FastAPI, oracledb    |
| Database  | Oracle XE 21c                     |
| Frontend  | React 18, Recharts, Axios         |
| Agents    | Python 3.x + requests             |
| Container | Docker, docker-compose, Nginx     |

---

## License

Internal use only — RecSignal DevOps Platform.
