import json
import sys
import asyncio

# Ensure UTF-8 output for emojis in summary
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from agents.orchestrator import (
    process_submission,
    process_batch,
    get_submission_status,
    setup_user_profile
)

async def run_demo():
    print("\n" + "="*60)
    print("MULTI-LINE SUBMISSION INTAKE AGENT — DEMO (A2A MODE)")
    print("="*60)

    print("\n--- Setting up user profiles ---")
    setup_user_profile("clerk_01", "clerk", "Priya")
    setup_user_profile("manager_01", "manager", "David")
    print("Profiles created")

    print("\n--- SCENARIO 1: Clerk processes SUB-001 ---")
    result = await process_submission("SUB-001", "clerk_01")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print("\nSUMMARY FOR CLERK:")
        print(result.get("summary", "No summary generated"))

    print("\n--- SCENARIO 2: Manager processes batch ---")
    batch = await process_batch(
        ["SUB-001", "SUB-002", "SUB-003", "SUB-005"],
        "manager_01"
    )
    print(f"\nBatch complete: {len(batch)} submissions")
    for r in batch:
        sid = r.get("submission_id", "unknown")
        queue = r.get("routing", {}).get("queue", "unknown")
        score = r.get("validation", {}).get(
            "completeness_score", 0
        )
        line = r.get("classification", {}).get(
            "primary_line", "unknown"
        )
        print(f"  {sid} | {line} | {score:.0%} | {queue}")

    print("\n--- SCENARIO 3: Status chat query ---")
    status = await get_submission_status("SUB-002")
    print(f"SUB-002 Status: {status.get('status')}")
    print(f"Queue: {status.get('routing', {}).get('queue', 'unknown')}")

    print("\n--- SCENARIO 4: Incomplete SUB-005 ---")
    result5 = await process_submission("SUB-005", "clerk_01")
    validation = result5.get("validation", {})
    routing = result5.get("routing", {})
    print(f"Completeness: {validation.get('completeness_score')}")
    print(f"Missing: {validation.get('missing_fields')}")
    print(f"Queue: {routing.get('queue')}")
    
    print("\n" + "="*60)
    print("ALL DEMO SCENARIOS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(run_demo())
