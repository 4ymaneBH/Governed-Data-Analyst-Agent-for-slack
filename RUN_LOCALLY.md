# Run Locally (Without Docker)

This guide explains how to run the Governed Data Analyst Agent natively on Windows.

## 1. Prerequisites

You must have the following installed:

1.  **Python 3.11+**
2.  **PostgreSQL 16+** ([Download for Windows](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads))
    *   During install, set password to `analyst_secret` (or update `.env`)
    *   Create database named `analyst_db`
3.  **Ollama** ([Download for Windows](https://ollama.com/download))
4.  **Open Policy Agent (OPA)**
    *   Download `opa_windows_amd64.exe` from [GitHub Releases](https://github.com/open-policy-agent/opa/releases)
    *   Rename to `opa.exe` and add to your system PATH.

## 2. Configuration Updates

Modify your `.env` file to use `localhost` instead of Docker container names:

```ini
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=analyst
POSTGRES_PASSWORD=analyst_secret
POSTGRES_DB=analyst_db

# Services
OPA_URL=http://localhost:8181
AGENT_URL=http://localhost:8002
MCP_SERVER_URL=http://localhost:8001
OLLAMA_BASE_URL=http://localhost:11434
```

## 3. Infrastructure Setup

### Database
Run the initialization scripts using `psql` (PowerShell):
```powershell
$env:PGPASSWORD="analyst_secret"
psql -h localhost -U analyst -d analyst_db -f infra/postgres/init.sql
psql -h localhost -U analyst -d analyst_db -f infra/postgres/seed.sql
```

### OPA Policy Engine
Start OPA with the policy directory:
```powershell
# Open a new terminal
opa run --server --addr :8181 ./policies/rego
```

### Ollama
Ensure Ollama is running and has the model:
```powershell
ollama pull llama3.2
ollama serve
```

## 4. Run Services (Python)

You will need to run **4 separate terminals**, one for each service.

### Service 1: MCP Server (Port 8001)
```powershell
cd services/mcp-server
pip install -r requirements.txt
python server.py
```

### Service 2: Agent Service (Port 8002)
```powershell
cd services/agent
pip install -r requirements.txt
python main.py
```

### Service 3: Admin UI (Port 8080)
```powershell
cd apps/admin-ui
pip install -r requirements.txt
python main.py
```

### Service 4: Slack App (Socket Mode)
```powershell
cd services/slack-app
pip install -r requirements.txt
python main.py
```

## 5. Verification
- Admin UI: http://localhost:8080
- Agent API: http://localhost:8002/docs
- OPA: http://localhost:8181/v1/policies
