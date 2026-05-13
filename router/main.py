import os
import sys
import json
import uvicorn
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

import tracing.arize_setup  # noqa: F401
from tracing.pipeline_context import execution_mode

_A2A_CARD_HOST = os.getenv("A2A_AGENT_HOST", "127.0.0.1")

# Import existing business logic (kept unchanged in agents/)
from agents.router import (
    determine_routing as _determine_routing,
    generate_summary as _generate_summary,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_A2A_STAGING_ROOT = os.path.join(BASE_DIR, "data", "a2a_staging")
_CANDIDATES_DIR = os.path.join(BASE_DIR, "data", "processed_candidates")


def _insured_name_from_parsed(parsed_data: list) -> str:
    for doc in parsed_data or []:
        if not isinstance(doc, dict):
            continue
        fields = doc.get("extracted_fields") or doc.get("extractedFields") or {}
        if isinstance(fields, dict):
            name = fields.get("insured_name")
            if name:
                return str(name)
        if doc.get("document_type") == "application" and isinstance(fields, dict):
            name = fields.get("insured_name")
            if name:
                return str(name)
    return "Unknown"


def _parse_first_json_object(raw: str) -> dict:
    """Parse a single JSON object; ignore trailing text (fixes 'Extra data' from LLM output)."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty JSON string")
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        obj, _end = json.JSONDecoder().raw_decode(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj


def _parse_json_array(raw: str) -> list:
    """Parse JSON array; tolerate trailing text from LLM."""
    s = (raw or "").strip()
    if not s:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(s)
    except json.JSONDecodeError:
        return []
    return obj if isinstance(obj, list) else []


def _safe_staging_file(staged_relative_path: str) -> str:
    """Resolve a path that must stay under data/a2a_staging/."""
    rel = (staged_relative_path or "").replace("\\", "/").strip().lstrip("/")
    if ".." in rel or rel.startswith("/"):
        raise ValueError("invalid staged path")
    if not rel.startswith("data/a2a_staging/"):
        raise ValueError("staged file must be under data/a2a_staging/")
    full = os.path.normpath(os.path.join(BASE_DIR, rel))
    root = os.path.normpath(_A2A_STAGING_ROOT)
    if not full.startswith(root + os.sep):
        raise ValueError("path outside staging directory")
    return full


async def _generate_intake_from_all_data(
    all_data: dict, submission_id: str, user_role: str
) -> str:
    parsed_data = all_data.get("parsed_data", [])
    routing_result = all_data.get("routing", {})
    v = all_data.get("validation", {})
    if isinstance(v, dict) and isinstance(v.get("validation"), dict) and (
        "completeness_score" in v["validation"] or "field_status" in v["validation"]
    ):
        inner = v["validation"]
        validation_result = {
            **inner,
            "classification": v.get("classification", inner.get("classification")),
            "line_of_business": v.get("line_of_business", inner.get("line_of_business")),
        }
    else:
        validation_result = v if isinstance(v, dict) else {}
    user_profile = {"role": user_role}
    return await _generate_summary(
        parsed_data, routing_result, user_profile, submission_id, validation_result
    )


async def determine_routing(
    line_of_business: str, completeness_score: float, missing_fields_json: str
) -> dict:
    """Determine the correct underwriting queue for a submission.

    Args:
        line_of_business: Classified line of business (e.g. commercial_auto).
        completeness_score: Completeness score from 0.0 to 1.0.
        missing_fields_json: JSON string array of missing field names.

    Returns:
        Dictionary with queue, routing_reason, priority, and action_needed.
    """
    with execution_mode("a2a_http_router"):
        validation_result = {
            "completeness_score": completeness_score,
            "missing_fields": _parse_json_array(missing_fields_json),
        }
        return await _determine_routing(line_of_business, validation_result)


async def generate_intake_summary(
    submission_id: str, all_data_json: str, user_role: str
) -> str:
    """Generate a formatted intake summary report.

    Args:
        submission_id: The submission ID (e.g. SUB-001).
        all_data_json: JSON string with all submission data including parsed_data,
                       routing, and validation results.
        user_role: Either 'clerk' or 'manager'.

    Returns:
        Formatted summary string.
    """
    with execution_mode("a2a_http_router"):
        all_data = _parse_first_json_object(all_data_json)
        return await _generate_intake_from_all_data(all_data, submission_id, user_role)


async def generate_intake_summary_from_staged_file(
    submission_id: str, user_role: str, staged_relative_path: str
) -> str:
    """Load intake payload JSON from disk (written by orchestrator); avoids huge tool args over A2A.

    staged_relative_path must be like ``data/a2a_staging/SUB-001_abc123.json`` (forward slashes).
    The file is deleted after a successful read.
    """
    with execution_mode("a2a_http_router"):
        path = _safe_staging_file(staged_relative_path)
        try:
            with open(path, encoding="utf-8") as f:
                all_data = json.load(f)
            if not isinstance(all_data, dict):
                raise ValueError("staged file must contain a JSON object")
            return await _generate_intake_from_all_data(all_data, submission_id, user_role)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


async def finalize_intake_summary_from_staged(
    submission_id: str,
    user_role: str,
    intake_payload_staged_relative_path: str,
    routing_json: str,
) -> dict:
    """Merge staged parsed+validation with routing, generate summary, write processed candidate JSON.

    Writes ``data/processed_candidates/{SUB}.json`` for the orchestrator ``commit_processed_intake`` tool.
    Deletes the intake payload staged file after success.
    """
    with execution_mode("a2a_http_router"):
        path = _safe_staging_file(intake_payload_staged_relative_path)
        with open(path, encoding="utf-8") as f:
            body = json.load(f)
        if not isinstance(body, dict):
            raise ValueError("intake payload must be a JSON object")
        routing = _parse_first_json_object(routing_json)
        parsed_data = body.get("parsed_data") or []
        if not isinstance(parsed_data, list):
            parsed_data = []
        v = body.get("validation")
        if not isinstance(v, dict):
            v = {}
        all_data = {
            "parsed_data": parsed_data,
            "validation": v,
            "routing": routing,
        }
        sid = submission_id.strip().upper()
        summary = await _generate_intake_from_all_data(all_data, sid, user_role)
        classification = v.get("classification") if isinstance(v, dict) else None
        validation_inner = {
            k: val for k, val in v.items() if k not in ("classification", "line_of_business")
        } if isinstance(v, dict) else {}
        payload = {
            "submission_id": sid,
            "insured_name": _insured_name_from_parsed(parsed_data),
            "parsed_data": parsed_data,
            "classification": classification,
            "validation": validation_inner,
            "routing": routing,
            "summary": summary,
            "documents_processed": len(parsed_data),
        }
        os.makedirs(_CANDIDATES_DIR, exist_ok=True)
        cand_path = os.path.join(_CANDIDATES_DIR, f"{sid}.json")
        with open(cand_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        try:
            os.remove(path)
        except OSError:
            pass
        return {
            "success": True,
            "submission_id": sid,
            "summary": summary,
            "candidate_path": cand_path,
            "message": (
                "Summary generated; candidate saved. Orchestrator should call commit_processed_intake "
                f"with submission_id {sid}."
            ),
        }


from router.agent import root_agent as agent

app = to_a2a(agent, host=_A2A_CARD_HOST, port=8003, protocol="http")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
