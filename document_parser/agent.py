import os
import json
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from agents.document_parser import extract_fields as _extract_fields
from agents.document_parser import parse_submission

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

async def extract_fields(file_path: str, document_type: str) -> dict:
    """Extract structured fields from an insurance document."""
    fp = file_path
    if not os.path.isabs(fp):
        fp = os.path.join(BASE_DIR, fp)

    with open(fp, "r", encoding="utf-8") as f:
        document_content = json.load(f)

    if document_type == "auto":
        from agents.document_parser import get_document_type
        document_type = get_document_type(fp)

    return await _extract_fields(document_content, document_type)

root_agent = Agent(
    name="document_parser",
    model="gemini-2.5-flash",
    instruction="""
    You are a document parser specialist.
    When asked to parse a submission ID (e.g. SUB-XXX):
    1. Call parse_submission with the submission_id
    2. Return the EXACT JSON array output to the caller
    
    When asked to parse a specific document:
    1. Call extract_fields with the file_path and document_type
    2. Return the extracted fields JSON
    
    Never invent data. Only return tool outputs.
    """,
    tools=[FunctionTool(extract_fields), FunctionTool(parse_submission)]
)
