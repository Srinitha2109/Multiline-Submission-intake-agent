import os
import json
from google.adk.agents import Agent
from google.adk.tools import FunctionTool, AgentTool
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def list_submission_documents(submission_id: str) -> list:
    """Lists all document paths in a submission folder.
    
    Args:
        submission_id: The submission ID (e.g. SUB-001)
    """
    submissions_dir = os.path.join(BASE_DIR, "data", "submissions", submission_id)
    if not os.path.exists(submissions_dir):
        return []
    
    docs = []
    for f in os.listdir(submissions_dir):
        if os.path.isfile(os.path.join(submissions_dir, f)):
            docs.append(os.path.join(submissions_dir, f))
    return docs

def save_processed_result(submission_id: str, result_content: str) -> str:
    """Save complete result to data/processed/{submission_id}.json"""
    path = os.path.join(BASE_DIR, "data", "processed", f"{submission_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        try:
            data = json.loads(result_content)
            json.dump(data, f, indent=2)
        except json.JSONDecodeError:
            f.write(result_content)
    return f"Saved successfully to {path}"

def load_processed_result(submission_id: str) -> str:
    """Load data/processed/{submission_id}.json"""
    path = os.path.join(BASE_DIR, "data", "processed", f"{submission_id}.json")
    if not os.path.exists(path):
        return "Submission not found."
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def manage_user_profile(user_id: str, role: str) -> str:
    """Save answer to data/user_profiles/{user_id}.json"""
    path = os.path.join(BASE_DIR, "data", "user_profiles", f"{user_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"role": role}, f)
    return "Profile saved."

document_parser = RemoteA2aAgent(
    name="document_parser",
    description="""
    Specialist agent that extracts structured fields from 
    insurance submission documents including applications,
    fleet schedules, property schedules, and loss history.
    Send it a file_path and document_type to parse.
    """,
    agent_card=f"http://localhost:8001{AGENT_CARD_WELL_KNOWN_PATH}"
)

validator = RemoteA2aAgent(
    name="validator",
    description="""
    Specialist agent that classifies line of business 
    (commercial_auto, commercial_property, general_liability, multi_line)
    and validates completeness of parsed submission data.
    Send it the combined parsed data from all documents.
    """,
    agent_card=f"http://localhost:8002{AGENT_CARD_WELL_KNOWN_PATH}"
)

router = RemoteA2aAgent(
    name="router",
    description="""
    Specialist agent that routes submissions to the correct 
    underwriting queue and generates intake summary report.
    Send it the validation results and user role.
    """,
    agent_card=f"http://localhost:8003{AGENT_CARD_WELL_KNOWN_PATH}"
)

root_agent = Agent(
    name="intake_orchestrator",
    model="gemini-2.5-pro",
    instruction="""
    You are an insurance submission intake orchestrator.
    You have 3 specialist sub-agents:
      - document_parser: parses documents and extracts fields
      - validator: classifies line of business and validates completeness
      - router: routes to underwriting queue and generates summary

    PIPELINE MODE — when user says process SUB-XXX:

      Step 1: PARSE DOCUMENTS
      Call the document_parser tool with message:
      "Parse the submission ID: <submission_id>"
      Wait for response. It will return the combined parsed JSON for all documents.

      Step 2: VALIDATE AND CLASSIFY
      Call the validator tool with message:
      "Classify and validate this parsed data: <combined_parsed_json>"
      Wait for validation response.

      Step 3: ROUTE AND SUMMARIZE
      Call the router tool with message:
      "Route this submission and generate summary:
       parsed_data_json=<combined_parsed_json_from_step_1>
       validation_results_json=<validation_results_from_step_2>
       submission_id=<id>
       user_role=<role>"
      Wait for response. The router will return the formatted Markdown summary.

      Step 4: SAVE AND RETURN
      Save the exact Markdown summary string returned by the router to data/processed/<submission_id>.json using the save_processed_result tool.
      Return EXACTLY the markdown summary produced by the router to the user. Do NOT output JSON or wrap it in a code block.

    CHAT MODE — when user asks about status:
      Load data/processed/<submission_id>.json using load_processed_result.
      Return status based on user role:
        clerk   = verbose with field details and next steps
        manager = concise table with key metrics only

    On first interaction, output EXACTLY this greeting:
    "Welcome to the Insurance Submission Intake System! I can help you process and track insurance submissions.
    Are you an operations clerk processing submissions, or a manager reviewing results?

    You can also ask me to:
    Process a submission: 'process submission SUB-001'
    Check status: 'what is the status of SUB-003'
    List submissions: 'show all submissions'"
    Save answer to data/user_profiles/<user_id>.json using manage_user_profile.

    CRITICAL RULES:
    - NEVER call validator before document_parser completes
    - NEVER call router before validator completes
    - Call the sub-agents as tools. For example, call document_parser with a message instructing it what to parse.
    - NEVER invent or assume submission data
    - Only use outputs returned by sub-agents
    """,
    tools=[
        AgentTool(agent=document_parser),
        AgentTool(agent=validator),
        AgentTool(agent=router),
        FunctionTool(save_processed_result),
        FunctionTool(load_processed_result),
        FunctionTool(manage_user_profile)
    ]
)
