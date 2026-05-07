import sys
import os
import yaml
from google.adk import Agent
from google.adk.tools import FunctionTool

# Add parent directory to sys.path to allow imports from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import tracing.arize_setup

from agents.orchestrator import (
    process_submission as orchestrator_process,
    process_batch as orchestrator_batch,
    get_submission_status as orchestrator_status,
    setup_user_profile as orchestrator_setup,
    get_submissions_by_queue as orchestrator_query_queue
)

# Load config
with open(os.path.join(os.path.dirname(__file__), "root_agent.yaml"), "r") as f:
    config = yaml.safe_load(f)

# Hard-remove tools and sub_agents from config to prevent Pydantic collisions
if "tools" in config: del config["tools"]
if "sub_agents" in config: del config["sub_agents"]

# Create the agent
agent = Agent(**config)

# Register tools explicitly
async def process_submission(submission_id: str, user_id: str = "default_user"):
    """Run full pipeline for one insurance submission."""
    return await orchestrator_process(submission_id, user_id)

async def process_batch(submission_ids: list[str], user_id: str = "default_user"):
    """Run pipeline for multiple insurance submissions."""
    return await orchestrator_batch(submission_ids, user_id)

async def get_submission_status(submission_id: str, user_id: str = "default_user"):
    """Look up the status and results of a processed submission."""
    return await orchestrator_status(submission_id, user_id)

async def manage_user_profile(user_id: str, role: str, name: str = ""):
    """Setup or update a user profile (clerk or manager)."""
    return orchestrator_setup(user_id, role, name)

async def get_submissions_by_queue(queue_name: str = "all"):
    """
    Search and list processed submissions. 
    Use queue_name='all' to get every submission or total count.
    """
    return await orchestrator_query_queue(queue_name)

# FORCE REGISTRATION
agent.tools = [
    FunctionTool(func=process_submission),
    FunctionTool(func=process_batch),
    FunctionTool(func=get_submission_status),
    FunctionTool(func=manage_user_profile),
    FunctionTool(func=get_submissions_by_queue)
]

# Final exposure
root_agent = agent
