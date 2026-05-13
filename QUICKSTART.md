# Quick Start Guide - A2A Multi-Agent System

## Installation

```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Install/upgrade dependencies
pip install --upgrade google-adk a2a-sdk
pip install -r requirements.txt

# 3. Verify .env file has GOOGLE_API_KEY set
```

## Running the System

### Option 1: Manual (Recommended for first time)

Open **4 separate terminal windows**, activate venv in each, then run:

**Terminal 1:**
```powershell
python document_parser/main.py
```
Wait for: `INFO:     Uvicorn running on http://0.0.0.0:8001`

**Terminal 2:**
```powershell
python validator/main.py
```
Wait for: `INFO:     Uvicorn running on http://0.0.0.0:8002`

**Terminal 3:**
```powershell
python router/main.py
```
Wait for: `INFO:     Uvicorn running on http://0.0.0.0:8003`

**Terminal 4:**
```powershell
adk web
```
Wait for: `INFO:     Uvicorn running on http://127.0.0.1:8000`

Then open: **http://localhost:8000**

### Option 2: Automated

```powershell
python start_agents.py
```

This opens 3 windows for specialist agents. Then manually run `adk web` in a 4th terminal.

## Testing

1. Open http://localhost:8000
2. Select `intake_orchestrator` from dropdown
3. Type: `hello`
4. Type: `I am a clerk`
5. Type: `process submission SUB-001`
6. Type: `what is the status of SUB-001`

## Stopping

Press `Ctrl+C` in each terminal window to stop the agents.

## Troubleshooting

**"Connection refused" error:**
- Make sure all 3 specialist agents (ports 8001, 8002, 8003) are running BEFORE starting `adk web`

**"Port already in use":**
```powershell
# Find process using port
netstat -ano | findstr :8001

# Kill process (replace <PID> with actual number)
taskkill /PID <PID> /F
```

**Agent not responding:**
- Check all 3 specialist agent terminals show "Uvicorn running"
- Restart agents in order: parser → validator → router → orchestrator

**Import errors:**
```powershell
pip install --upgrade google-adk>=1.2.0 a2a-sdk>=0.9.0
```
