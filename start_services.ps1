# PowerShell script to start all Python services in separate windows
Write-Host "Starting Data Analyst Agent Services..." -ForegroundColor Cyan

# Check if Python is installed
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not in PATH."
    exit 1
}

# Function to start a process in a new window
function Start-ServiceWindow {
    param(
        [string]$Name,
        [string]$Path,
        [string]$Command
    )
    Write-Host "Starting $Name..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Path'; Write-Host 'Installing dependencies for $Name...'; pip install -r requirements.txt; if ($?) { Write-Host 'Starting $Name...'; $Command } else { Write-Error 'Install failed' }"
}

# 1. MCP Server
Start-ServiceWindow -Name "MCP Tool Server" -Path "services/mcp-server" -Command "python server.py"

# 2. Agent Service
Start-ServiceWindow -Name "Agent Service" -Path "services/agent" -Command "python main.py"

# 3. Admin UI
Start-ServiceWindow -Name "Admin UI" -Path "apps/admin-ui" -Command "python main.py"

# 4. Slack App
Start-ServiceWindow -Name "Slack App" -Path "services/slack-app" -Command "python main.py"

Write-Host "All service windows launched!" -ForegroundColor Cyan
Write-Host "Ensure Postgres (localhost:5432), OPA (localhost:8181), and Ollama (localhost:11434) are running first." -ForegroundColor Yellow
