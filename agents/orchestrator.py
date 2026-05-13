import json
import os
from datetime import datetime
from dotenv import load_dotenv

from agents.document_parser import parse_submission
from agents.validator import run_validation_and_classification
from agents.router import determine_routing, generate_summary
from profiles.user_profile_manager import UserProfileManager

load_dotenv()
profile_manager = UserProfileManager()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _insured_name_from_parsed(parsed_data: list) -> str:
    for doc in parsed_data or []:
        if not isinstance(doc, dict):
            continue
        fields = doc.get("extracted_fields") or doc.get("extractedFields") or {}
        if isinstance(fields, dict) and fields.get("insured_name"):
            return str(fields["insured_name"])
    return "Unknown"


async def process_submission(
    submission_id: str,
    user_id: str = "default_user",
) -> dict:
    """Parse, validate, route, and summarize a submission (in-process; no HTTP A2A)."""
    user_profile = profile_manager.get(user_id)
    role = user_profile.get("role") or "clerk"
    if role not in ("clerk", "manager"):
        role = "clerk"

    print(f"\n{'='*50}")
    print(f"Processing: {submission_id}")
    print(f"{'='*50}")

    folder = os.path.join(BASE_DIR, f"data/submissions/{submission_id}")
    if not os.path.exists(folder):
        return {
            "error": f"Submission {submission_id} not found",
            "available": os.listdir(os.path.join(BASE_DIR, "data/submissions")),
        }

    print("\nSTEP 1: Parsing documents...")
    parsed_data = await parse_submission(submission_id)
    print(f"Parsed {len(parsed_data)} documents")

    print("\nSTEP 2: Validating and classifying...")
    validation_result = await run_validation_and_classification(parsed_data)
    line = validation_result["line_of_business"]
    score = validation_result["validation"]["completeness_score"]
    print(f"LOB: {line} | Completeness: {score * 100:.0f}%")

    print("\nSTEP 3: Routing and summarizing...")
    vinner = validation_result["validation"]
    routing_data = await determine_routing(line, vinner)
    validation_for_summary = {
        **vinner,
        "classification": validation_result.get("classification"),
        "line_of_business": line,
    }
    summary_data = await generate_summary(
        parsed_data,
        routing_data,
        {"role": role},
        submission_id,
        validation_for_summary,
    )
    print(f"Queue: {routing_data.get('queue', 'Unknown')}")

    result = {
        "submission_id": submission_id,
        "insured_name": _insured_name_from_parsed(parsed_data),
        "status": "complete",
        "processed_at": datetime.now().isoformat(),
        "documents_processed": len(parsed_data),
        "classification": validation_result["classification"],
        "validation": validation_result["validation"],
        "routing": routing_data,
        "summary": summary_data,
        "user_role": user_profile.get("role"),
    }

    processed_dir = os.path.join(BASE_DIR, "data/processed")
    os.makedirs(processed_dir, exist_ok=True)
    path = os.path.join(processed_dir, f"{submission_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Saved to data/processed/{submission_id}.json")
    return result


async def process_batch(
    submission_ids: list[str],
    user_id: str = "default_user",
) -> list:
    results = []
    for submission_id in submission_ids:
        result = await process_submission(submission_id, user_id)
        results.append(result)
    return results


async def get_submission_status(
    submission_id: str,
    user_id: str = "default_user",
) -> dict:
    """Get the current status and details of a processed submission."""
    processed_dir = os.path.join(BASE_DIR, "data/processed")
    path = os.path.join(processed_dir, f"{submission_id}.json")

    if not os.path.exists(path):
        available = os.listdir(processed_dir) if os.path.exists(processed_dir) else []
        return {
            "success": False,
            "error": f"Submission {submission_id} has not been processed yet.",
            "available_submissions": [f.replace(".json", "") for f in available if f.endswith(".json")],
        }

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    insured_name = (
        data.get("validation", {}).get("field_status", {}).get("insured_name", {}).get("value")
        or data.get("insured_name")
        or "Unknown"
    )

    completeness = data.get("validation", {}).get("completeness_score", 0)
    routing = data.get("routing", {})

    return {
        "success": True,
        "submission_id": submission_id,
        "insured_name": insured_name,
        "status": data.get("status", "processed"),
        "queue": routing.get("queue", "Unknown"),
        "priority": routing.get("priority", "normal"),
        "action_needed": routing.get("action_needed", "none"),
        "completeness_score": f"{int(completeness * 100)}%",
        "documents_processed": data.get("documents_processed", 0),
        "processed_at": data.get("processed_at", "Unknown"),
        "message": (
            f"Submission {submission_id} for {insured_name} has been processed and routed to "
            f"{routing.get('queue', 'Unknown')}."
        ),
    }


def setup_user_profile(
    user_id: str,
    role: str,
    name: str = "",
) -> dict:
    return profile_manager.update(
        user_id,
        {"role": role, "name": name},
    )


async def get_submissions_by_queue(queue_name: str = "all") -> dict:
    """Scan processed submissions and return list filtered by queue name."""
    processed_dir = os.path.join(BASE_DIR, "data/processed")
    results = []

    if not os.path.exists(processed_dir):
        return {
            "success": False,
            "message": "No processed submissions found.",
            "submissions": [],
        }

    for filename in os.listdir(processed_dir):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(processed_dir, filename), encoding="utf-8") as f:
                data = json.load(f)

            submission_queue = data.get("routing", {}).get("queue", "Unknown")
            insured_name = (
                data.get("validation", {}).get("field_status", {}).get("insured_name", {}).get("value")
                or data.get("insured_name")
                or "Unknown"
            )

            if not queue_name or queue_name.lower() == "all" or queue_name.lower() in submission_queue.lower():
                results.append({
                    "submission_id": data["submission_id"],
                    "insured_name": insured_name,
                    "queue": submission_queue,
                    "status": data.get("status"),
                    "priority": data.get("routing", {}).get("priority", "normal"),
                })
        except Exception:
            continue

    return {
        "success": True,
        "queue_filter": queue_name if queue_name else "all",
        "total_count": len(results),
        "submissions": results,
        "message": f"Found {len(results)} submission(s) in {queue_name if queue_name else 'all queues'}.",
    }
