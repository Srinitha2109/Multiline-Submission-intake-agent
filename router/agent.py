import json
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from agents.router import run_routing_and_summary

async def generate_summary_and_routing(parsed_data_json: str, validation_results_json: str, submission_id: str, user_role: str) -> str:
    """Determine routing and generate summary."""
    try:
        parsed_data = json.loads(parsed_data_json)
        if isinstance(parsed_data, dict) and "documents" in parsed_data:
            parsed_data = parsed_data["documents"]
        elif not isinstance(parsed_data, list):
            parsed_data = [parsed_data]
    except:
        parsed_data = []

    try:
        val_results = json.loads(validation_results_json)
    except:
        val_results = {}
        
    line = val_results.get("line_of_business", "unknown")
    validation = val_results.get("validation", {})
    
    res = await run_routing_and_summary(parsed_data, line, validation, {"role": user_role}, submission_id)
    return res.get("summary", "")

root_agent = Agent(
    name="router",
    model="gemini-2.5-flash",
    instruction="""
    You are a routing and summary specialist.
    When given submission data:
    1. Call generate_summary_and_routing with parsed_data_json, validation_results_json, submission_id, and user_role.
    2. Return EXACTLY the verbatim markdown string returned by the tool. Do NOT wrap it in a JSON object or add code block formatting.
    """,
    tools=[FunctionTool(generate_summary_and_routing)]
)

