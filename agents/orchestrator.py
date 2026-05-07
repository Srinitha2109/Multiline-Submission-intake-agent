import json
import os
from datetime import datetime
from dotenv import load_dotenv
from tracing.arize_setup import setup_arize, get_tracer
from a2a.a2a_client import A2AClient
from profiles.user_profile_manager import UserProfileManager

load_dotenv()
profile_manager = UserProfileManager()

# Initialize A2A Clients
parser_client = A2AClient("a2a/agent_cards/document_parser_card.json")
validator_client = A2AClient("a2a/agent_cards/validator_card.json")
router_client = A2AClient("a2a/agent_cards/router_card.json")

async def process_submission(
    submission_id: str,
    user_id: str = "default_user"
) -> dict:
    user_profile = profile_manager.get(user_id)

    print(f"\n{'='*50}")
    print(f"Processing: {submission_id}")
    print(f"{'='*50}")

    print(f"\nSTEP 1: Loading documents...")
    folder = f"data/submissions/{submission_id}"
    if not os.path.exists(folder):
        return {
            "error": f"Submission {submission_id} not found",
            "available": os.listdir("data/submissions")
        }

    print(f"\nSTEP 2: Parsing all documents via A2A...")
    task_res = await parser_client.send_task("parse_submission", {"submission_id": submission_id})
    if "error" in task_res: return task_res
    parsed_data = task_res["output"]
    print(f"Parsed {len(parsed_data)} documents")

    print(f"\nSTEP 3: Validating and classifying via A2A...")
    task_res = await validator_client.send_task("run_validation_and_classification", {"parsed_data": parsed_data})
    if "error" in task_res: return task_res
    validation_result = task_res["output"]
    
    line = validation_result["line_of_business"]
    score = validation_result["validation"]["completeness_score"]
    print(f"LOB: {line} | Completeness: {score*100}%")

    print(f"\nSTEP 4: Routing and summarizing via A2A...")
    task_res = await router_client.send_task("run_routing_and_summary", {
        "parsed_data": parsed_data,
        "line_of_business": line,
        "validation_result": validation_result["validation"],
        "user_profile": user_profile,
        "submission_id": submission_id
    })
    if "error" in task_res: return task_res
    routing_result = task_res["output"]
    
    print(f"Queue: {routing_result['routing']['queue']}")

    result = {
        "submission_id": submission_id,
        "status": "complete",
        "processed_at": datetime.now().isoformat(),
        "documents_processed": len(parsed_data),
        "classification": validation_result["classification"],
        "validation": validation_result["validation"],
        "routing": routing_result["routing"],
        "summary": routing_result["summary"],
        "user_role": user_profile.get("role")
    }

    if not os.path.exists("data/processed"):
        os.makedirs("data/processed")
        
    with open(f"data/processed/{submission_id}.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"Saved to data/processed/{submission_id}.json")
    return result

async def process_batch(
    submission_ids: list[str],
    user_id: str = "default_user") -> list:
    results = []
    for submission_id in submission_ids:
        result = await process_submission(
            submission_id, user_id
        )
        results.append(result)
    return results

async def get_submission_status(
    submission_id: str,
    user_id: str = "default_user"
) -> dict:
    path = f"data/processed/{submission_id}.json"
    if not os.path.exists(path):
        available = os.listdir("data/processed") if os.path.exists("data/processed") else []
        return {
            "error": f"Status for {submission_id} not found",
            "available_submissions": available
        }
    with open(path) as f:
        data = json.load(f)
        
        return {
            "submission_id": data.get("submission_id"),
            "insured_name": data.get("insured_name"),
            "status": data.get("status", "Processed"),
            "queue": data.get("routing", {}).get("queue", "Unknown"),
            "priority": data.get("routing", {}).get("priority", "Normal"),
            "action_needed": data.get("routing", {}).get("action_needed", "None"),
            "completeness_score": data.get("validation", {}).get("completeness_score", 0)
        }

def setup_user_profile(
    user_id: str,
    role: str,
    name: str = ""
) -> dict:
    return profile_manager.update(
        user_id,
        {"role": role, "name": name}
    )

async def get_submissions_by_queue(queue_name: str = "all") -> list:
    """
    Scan processed submissions. Use 'all' or empty string to get total count.
    """
    processed_dir = "data/processed"
    results = []
    if not os.path.exists(processed_dir):
        return []

    for filename in os.listdir(processed_dir):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(processed_dir, filename)) as f:
                    data = json.load(f)

                submission_queue = data.get("routing", {}).get("queue", "Unknown")

                # If queue_name is 'all' or empty, or matches specifically
                if not queue_name or queue_name.lower() == "all" or queue_name.lower() in submission_queue.lower():
                    results.append({
                        "submission_id": data["submission_id"],
                        "insured_name": data.get("insured_name", "Unknown"),
                        "queue": submission_queue,
                        "status": data.get("status")
                    })
            except:
                continue

    return results
