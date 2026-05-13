import os
import sys
import json
import uuid
import uvicorn
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

import tracing.arize_setup  # noqa: F401 — OTel + Arize when specialist runs standalone
from tracing.pipeline_context import execution_mode

# Import existing business logic (kept unchanged in agents/)
from agents.document_parser import (
    load_document,
    get_document_type,
    extract_fields as _extract_fields,
    parse_submission,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_A2A_STAGING_ROOT = os.path.join(BASE_DIR, "data", "a2a_staging")
# Host embedded in the served AgentCard RPC url — keep in sync with intake_orchestrator A2A_AGENT_HOST.
_A2A_CARD_HOST = os.getenv("A2A_AGENT_HOST", "127.0.0.1")


def _write_parsed_documents_staging(submission_id: str, documents: list) -> str:
    """Write parsed documents JSON array for validator/router (avoids huge tool-arg strings)."""
    os.makedirs(_A2A_STAGING_ROOT, exist_ok=True)
    name = f"{submission_id}_parsed_{uuid.uuid4().hex[:12]}.json"
    rel = f"data/a2a_staging/{name}"
    full = os.path.normpath(os.path.join(BASE_DIR, rel.replace("/", os.sep)))
    root = os.path.normpath(_A2A_STAGING_ROOT)
    if not full.startswith(root + os.sep):
        raise ValueError("invalid staging path")
    with open(full, "w", encoding="utf-8") as f:
        json.dump(documents, f)
    return rel


async def extract_fields(file_path: str, document_type: str) -> dict:
    """Extract structured fields from an insurance document.

    Args:
        file_path: Path to the JSON document file, or a submission ID (e.g. SUB-001).
        document_type: Type of document (application, fleet_schedule, loss_history, etc.).
                       Use 'auto' to detect from filename.

    Returns:
        Dictionary with extracted fields, confidence score, and notes.
    """
    with execution_mode("a2a_http_document_parser"):
        # If file_path looks like a submission ID, parse all documents in that folder
        if file_path.upper().startswith("SUB-"):
            sid = file_path.upper()
            results = await parse_submission(sid)
            staged_rel = _write_parsed_documents_staging(sid, results)
            return {
                "submission_id": sid,
                "documents": results,
                "count": len(results),
                "parsed_data_staged_path": staged_rel,
            }

        # Resolve relative paths against project root
        fp = file_path
        if not os.path.isabs(fp):
            fp = os.path.join(BASE_DIR, fp)

        document_content = load_document(fp)

        dt = document_type
        if dt == "auto":
            dt = get_document_type(fp)

        result = await _extract_fields(document_content, dt)
        return result


from document_parser.agent import root_agent as agent

# A2A Starlette app: serves /.well-known/agent.json (deprecated), /.well-known/agent-card.json, and POST /
app = to_a2a(agent, host=_A2A_CARD_HOST, port=8001, protocol="http")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
