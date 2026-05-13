import json
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from agents.validator import classify_line_of_business as _classify_line_of_business
from agents.validator import validate_completeness as _validate_completeness

def _parse_json(raw: str) -> list:
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\\n")
        s = "\\n".join(lines[1:-1]).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, list) else [obj]
    except:
        return []

async def classify_line_of_business(parsed_data_json: str) -> dict:
    """Classify the line of business."""
    return await _classify_line_of_business(_parse_json(parsed_data_json))

async def validate_completeness(parsed_data_json: str, line_of_business: str) -> dict:
    """Validate completeness."""
    return await _validate_completeness(_parse_json(parsed_data_json), line_of_business)

root_agent = Agent(
    name="validator",
    model="gemini-2.5-pro",
    instruction="""
    You are a validation and classification specialist.
    When given parsed document data:
    1. Call classify_line_of_business with the parsed data
    2. Call validate_completeness with parsed data and the classified line
    3. Return both results combined
    Never invent data. Only return tool outputs.
    """,
    tools=[FunctionTool(classify_line_of_business),
           FunctionTool(validate_completeness)]
)
