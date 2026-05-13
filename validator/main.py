import os
import re
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

import tracing.arize_setup  # noqa: F401
from tracing.pipeline_context import execution_mode

_A2A_CARD_HOST = os.getenv("A2A_AGENT_HOST", "127.0.0.1")

# Import existing business logic (kept unchanged in agents/)
from agents.validator import (
    classify_line_of_business as _classify_lob,
    validate_completeness as _validate_completeness,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_A2A_STAGING_ROOT = os.path.join(BASE_DIR, "data", "a2a_staging")


def _safe_staging_file(staged_relative_path: str) -> str:
    rel = (staged_relative_path or "").replace("\\", "/").strip().lstrip("/")
    if ".." in rel or rel.startswith("/"):
        raise ValueError("invalid staged path")
    if not rel.startswith("data/a2a_staging/"):
        raise ValueError("staged file must be under data/a2a_staging/")
    full = os.path.normpath(os.path.join(BASE_DIR, rel.replace("/", os.sep)))
    root = os.path.normpath(_A2A_STAGING_ROOT)
    if not full.startswith(root + os.sep):
        raise ValueError("path outside staging directory")
    return full


def _strip_markdown_json_fence(raw: str) -> str:
    s = (raw or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_parsed_data_json_string(raw: str) -> list:
    """Parse JSON array or extract_fields-shaped dict; tolerate trailing junk / fences."""
    s = _strip_markdown_json_fence(raw)
    if not s:
        raise ValueError("empty parsed_data_json")
    obj, _end = json.JSONDecoder().raw_decode(s)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        docs = obj.get("documents")
        if isinstance(docs, list):
            return docs
    raise ValueError("parsed_data_json must be a JSON array or object with documents[]")


def _load_parsed_list_from_staged_file(staged_relative_path: str) -> list:
    path = _safe_staging_file(staged_relative_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("documents"), list):
        return data["documents"]
    raise ValueError("staged parsed file must be a JSON array or {documents: []}")


def _write_intake_payload_staging(submission_hint: str, payload: dict) -> str:
    os.makedirs(_A2A_STAGING_ROOT, exist_ok=True)
    name = f"{submission_hint}_intake_partial_{uuid.uuid4().hex[:12]}.json"
    rel = f"data/a2a_staging/{name}"
    full = _safe_staging_file(rel)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=str)
    return rel


async def classify_line_of_business(parsed_data_json: str) -> dict:
    """Classify the line of business for an insurance submission.

    Args:
        parsed_data_json: JSON string of parsed document data (list of document dicts).

    Returns:
        Dictionary with primary_line, confidence, and reasoning.
    """
    with execution_mode("a2a_http_validator"):
        parsed_data = _parse_parsed_data_json_string(parsed_data_json)
        return await _classify_lob(parsed_data)


async def validate_completeness(parsed_data_json: str, line_of_business: str) -> dict:
    """Validate completeness of an insurance submission against required fields.

    Args:
        parsed_data_json: JSON string of parsed document data (list of document dicts).
        line_of_business: The classified line of business (e.g. commercial_auto).

    Returns:
        Dictionary with completeness_score, field_status, missing_fields, and validation_notes.
    """
    with execution_mode("a2a_http_validator"):
        parsed_data = _parse_parsed_data_json_string(parsed_data_json)
        return await _validate_completeness(parsed_data, line_of_business)


async def classify_and_validate_from_staged_file(staged_relative_path: str) -> dict:
    """Load parsed documents from disk, classify LOB, validate completeness, stage merged payload for router.

    Prefer this when document_parser returned parsed_data_staged_path (avoids huge JSON in tool args).
    Deletes the input staged parsed file after a successful read.
    """
    with execution_mode("a2a_http_validator"):
        path = _safe_staging_file(staged_relative_path)
        base = os.path.basename(path).upper()
        m = re.match(r"(SUB-[A-Z0-9-]+)_", base)
        sid = m.group(1) if m else "SUB-UNKNOWN"
        parsed_data = _load_parsed_list_from_staged_file(staged_relative_path)
        cls = await _classify_lob(parsed_data)
        line = cls.get("primary_line") or "unknown"
        val = await _validate_completeness(parsed_data, line)
        merged_validation = {
            "classification": cls,
            "line_of_business": line,
            **val,
        }
        intake_rel = _write_intake_payload_staging(
            sid,
            {"parsed_data": parsed_data, "validation": merged_validation},
        )
        try:
            os.remove(path)
        except OSError:
            pass

        return {
            "classification": cls,
            "line_of_business": line,
            "validation": val,
            "completeness_score": val.get("completeness_score"),
            "missing_fields": val.get("missing_fields"),
            "intake_payload_staged_path": intake_rel,
        }


from validator.agent import root_agent as agent

app = to_a2a(agent, host=_A2A_CARD_HOST, port=8002, protocol="http")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
