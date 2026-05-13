# 🏢 Insurance Submission Intake — Multi-Agent System with A2A Protocol

A distributed multi-agent insurance submission intake system built with **Google's Agent Development Kit (ADK)** and the **Agent-to-Agent (A2A) protocol**. An orchestrator agent coordinates specialized remote sub-agents to parse, validate, classify, and route insurance submissions through natural conversation.

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      User (Browser)                      │
│                    adk web  →  :8000                     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│          IntakeOrchestrator  (intake_orchestrator/)      │
│        google.adk Agent  +  RemoteA2aAgent sub-agents   │
│          Runs via:  adk web  (port 8000)                 │
└──────────┬──────────────┬──────────────┬────────────────┘
           │  A2A         │  A2A         │  A2A
           ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ DocumentParser│  │  Validator   │  │    Router    │
│document_parser│  │ validator/  │  │  router/     │
│  main.py      │  │  main.py    │  │  main.py     │
│uvicorn :8001  │  │uvicorn :8002 │  │uvicorn :8003 │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Components

| Component | File | Port | Role |
|---|---|---|---|
| **IntakeOrchestrator** | `intake_orchestrator/agent.py` | 8000 (via `adk web`) | Root agent — coordinates workflow, manages user profiles, provides status queries |
| **DocumentParser** | `document_parser/main.py` | 8001 | Specialist agent — parses insurance documents using LLM extraction |
| **Validator** | `validator/main.py` | 8002 | Specialist agent — classifies line of business and validates completeness |
| **Router** | `router/main.py` | 8003 | Specialist agent — determines routing queue and generates summaries |

---

## 📂 Project Structure

```
Multiline-Submission-intake-agent/
├── document_parser/
│   └── main.py              # DocumentParser A2A server (port 8001)
├── validator/
│   └── main.py              # Validator A2A server (port 8002)
├── router/
│   └── main.py              # Router A2A server (port 8003)
├── intake_orchestrator/
│   ├── agent.py             # IntakeOrchestrator root_agent definition
│   └── root_agent.yaml      # Agent configuration
├── agents/
│   ├── document_parser.py   # Core parsing logic
│   ├── validator.py         # Core validation logic
│   ├── router.py            # Core routing logic
│   └── llm_client.py        # LLM client wrapper
├── profiles/
│   └── user_profile_manager.py  # User role management
├── prompts/
│   └── prompt_manager.py    # Prompt templates
├── tracing/
│   └── arize_setup.py       # Observability setup
├── data/
│   ├── submissions/         # Input submission folders
│   └── processed/           # Output JSON results
├── .env                     # API keys and config
├── requirements.txt         # Python dependencies
├── start_agents.py          # Automated startup script
└── README.md
```

---

## ⚙️ Prerequisites

- **Python 3.10+**
- A **Google Gemini API Key** — get one free at [aistudio.google.com](https://aistudio.google.com)
- **4 separate terminal windows** (one per agent + orchestrator)

---

## 🚀 Setup & Installation

### 1. Navigate to the project

```powershell
cd Multiline-Submission-intake-agent
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **Note (Windows):** If you get a script execution policy error, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Ensure your `.env` file contains:

```env
# Google Gemini Configuration
GOOGLE_API_KEY=your_gemini_api_key_here
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_PROJECT=your-project-id
LLM_PROVIDER=vertex
LLM_MODEL=gemini-2.5-flash-lite
PARSER_MODEL=gemini-2.5-flash-lite
VALIDATOR_MODEL=gemini-2.5-flash-lite
ROUTER_MODEL=gemini-2.5-flash-lite

# A2A Protocol
AGENT_PROTOCOL_SECURITY=none

# Arize Observability (optional)
ARIZE_SPACE_ID=your_space_id
ARIZE_API_KEY=your_api_key
ARIZE_MODEL_ID=insurance-intake
ARIZE_MODEL_VERSION=1.0.0
```

> ⚠️ **Never commit your `.env` file or real API keys to version control.**

---

## ▶️ Running the System

You need **4 terminal windows**, all with the virtual environment activated (`.\.venv\Scripts\Activate.ps1`).

### Terminal 1 — Start the Document Parser Agent

```powershell
python document_parser/main.py
```

Expected output:
```
🔍 Starting DocumentParser Agent on port 8001...
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### Terminal 2 — Start the Validator Agent

```powershell
python validator/main.py
```

Expected output:
```
✅ Starting ValidatorAgent on port 8002...
INFO:     Uvicorn running on http://0.0.0.0:8002
```

### Terminal 3 — Start the Router Agent

```powershell
python router/main.py
```

Expected output:
```
🚦 Starting RouterAgent on port 8003...
INFO:     Uvicorn running on http://0.0.0.0:8003
```

### Terminal 4 — Start the Orchestrator UI

```powershell
adk web
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

> ⚠️ **Order matters!** Always start the sub-agents (parser, validator, router) **before** starting `adk web`, so the orchestrator can discover them via A2A.

### Alternative: Automated Startup

```powershell
python start_agents.py
```

This will open 3 terminal windows for the specialist agents. Then manually run `adk web` in a 4th terminal.

### Open the UI

Navigate to **http://localhost:8000** in your browser. Select **`intake_orchestrator`** from the agent dropdown and start chatting.

---

## 💬 How to Use

### Initial Greeting

```
User: hello
```

The agent will welcome you and ask if you're a clerk or manager.

### Process a Submission

```
User: process submission SUB-001
```

The orchestrator will:
1. Call **DocumentParser** → parse all documents in `data/submissions/SUB-001/`
2. Call **ValidatorAgent** → classify line of business and validate completeness
3. Call **RouterAgent** → determine queue and generate summary
4. Return a complete intake summary

### Check Status

```
User: what is the status of SUB-003
```

Returns: submission ID, insured name, queue, priority, action needed, completeness score.

### List Submissions

```
User: show all submissions
User: which submissions are in Auto Queue
```

Returns: list of processed submissions filtered by queue.

---

## 🔄 Request Flow (Step-by-Step)

```
User: "process submission SUB-001"
         │
         ▼
IntakeOrchestrator validates submission_id
         │
         ▼
Calls RemoteA2aAgent("ask_parser")
  → HTTP A2A request → DocumentParser on :8001
  → parse_submission_tool("SUB-001")
  → Returns: [{document_type, extracted_fields, confidence}, ...]
         │
         ▼
Calls RemoteA2aAgent("ask_validator")
  → HTTP A2A request → ValidatorAgent on :8002
  → validate_and_classify_tool(parsed_data)
  → Returns: {classification, line_of_business, validation}
         │
         ▼
Calls RemoteA2aAgent("ask_router")
  → HTTP A2A request → RouterAgent on :8003
  → route_and_summarize_tool(parsed_data, line, validation, user_profile, submission_id)
  → Returns: {routing: {queue, priority, action_needed}, summary}
         │
         ▼
IntakeOrchestrator saves result to data/processed/SUB-001.json
  → Returns summary to user ✅
```

---

## 🧠 What We Built & Why

### The Problem
Building a single monolithic agent that handles document parsing, validation, classification, routing, and summarization becomes brittle and hard to maintain. Specialized knowledge gets muddled, and hallucinations increase.

### The Solution — A2A Multi-Agent Architecture
We split responsibilities across four independent agents that communicate via the **Agent-to-Agent (A2A) protocol** — a standardized HTTP-based protocol for agent interoperability.

| Design Decision | Rationale |
|---|---|
| **Specialist sub-agents** | Each agent (DocumentParser, ValidatorAgent, RouterAgent) has a focused instruction set and specific tools, reducing hallucinations |
| **`RemoteA2aAgent` as sub-agents** | The orchestrator treats remote HTTP services as native sub-agents — no manual HTTP calls needed |
| **Anti-hallucination instructions** | All agents are explicitly instructed to *only* use tool outputs — never invent data |
| **Sequential workflow enforcement** | The orchestrator enforces: Parse → Validate → Route → Summary, preventing partial or out-of-order responses |
| **User profile management** | Maintains clerk vs. manager roles to tailor summaries |
| **`adk web` for UI** | ADK's built-in web UI provides an instant chat interface without building a frontend |

### Key Technologies

| Technology | Version | Purpose |
|---|---|---|
| `google-adk` | ≥ 1.2.0 | Agent framework, `Runner`, `RemoteA2aAgent` |
| `a2a-sdk` | ≥ 0.9.0 | A2A protocol utilities (`to_a2a` wrapper) |
| `fastapi` | latest | ASGI web framework for sub-agent servers |
| `uvicorn` | latest | ASGI server to run FastAPI apps |
| `python-dotenv` | latest | Load `.env` config at runtime |
| `google-generativeai` | latest | Gemini LLM client |

---

## 🛠️ Troubleshooting

| Issue | Fix |
|---|---|
| `Connection refused` on sub-agent call | Ensure all 3 specialist agents are running **before** `adk web` |
| `ValidationError` on `RemoteA2aAgent` | Make sure `google-adk >= 1.2.0` is installed |
| `GOOGLE_API_KEY` not found | Check `.env` exists in the project root and the venv is activated |
| Port already in use | Kill the process: `netstat -ano \| findstr :8001` then `taskkill /PID <pid> /F` |
| `ExecutionPolicy` error (Windows) | Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Agent not responding | Check all 3 specialist agents are running and accessible at their ports |
| KeyError in orchestrator | Ensure sub-agents return proper response format with `success` and `output` keys |

---

## 📝 Notes

- The LLM-based extraction, validation, and routing use **prompt templates** stored in `prompts/prompt_manager.py`.
- Session data is stored **in-memory** and is lost when the orchestrator restarts.
- The A2A implementation in ADK is marked **experimental** — expect potential breaking changes in future ADK releases.
- Observability traces are sent to **Arize Phoenix** if credentials are configured.

---

## 🎯 Next Steps

- **Connect to real data sources**: Replace mock data with actual insurance APIs
- **Add authentication**: Implement proper A2A security instead of `AGENT_PROTOCOL_SECURITY=none`
- **Persistent storage**: Replace in-memory session with database
- **Add more agents**: Create specialist agents for underwriting, pricing, etc.
- **Deploy to production**: Containerize agents and deploy to cloud infrastructure

---

## 📚 References

- [Google ADK Documentation](https://github.com/google/adk)
- [A2A Protocol Specification](https://github.com/google/adk/blob/main/docs/a2a.md)
- [Gemini API Documentation](https://ai.google.dev/docs)

---

**Built with ❤️ using Google ADK and A2A Protocol**
