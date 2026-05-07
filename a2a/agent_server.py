import sys
import os
import asyncio
from fastapi import FastAPI, Request
import uvicorn
from opentelemetry import trace, propagate
from opentelemetry.trace import Status, StatusCode

# Add project root to path to allow imports from agents.*
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.document_parser import parse_submission
from agents.validator import run_validation_and_classification
from agents.router import run_routing_and_summary

app = FastAPI()
AGENT_NAME = None

@app.get("/")
async def root():
    return {"status": "Agent Server is running", "agent": AGENT_NAME}

@app.get("/.well-known/agent.json")
async def get_agent_card():
    if not AGENT_NAME:
        return {"error": "Agent name not configured"}
    
    card_path = f"a2a/agent_cards/{AGENT_NAME}_card.json"
    if os.path.exists(card_path):
        import json
        with open(card_path, "r") as f:
            return json.load(f)
    return {"error": f"Card not found for {AGENT_NAME}"}


@app.post("/document_parser")
async def handle_document_parser(request: Request):
    # Extract incoming trace context to link spans
    ctx = propagate.extract(dict(request.headers))
    tracer = trace.get_tracer("document_parser_server")
    
    task = await request.json()
    skill_id = task.get("skill_id")
    input_data = task.get("input", {})
    print(f"Document Parser received skill: {skill_id}")
    
    with tracer.start_as_current_span(f"agent_server.document_parser.{skill_id}", context=ctx) as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("a2a.skill_id", skill_id)
        try:
            if skill_id in ["parse_submission", "parse_application", "parse_schedule", "parse_loss_history"]:
                result = await parse_submission(input_data["submission_id"])
                span.set_status(Status(StatusCode.OK))
                return result
            span.set_status(Status(StatusCode.ERROR, f"Unknown skill: {skill_id}"))
            return {"error": f"Skill {skill_id} not implemented for Document Parser"}
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            return {"error": str(e)}


@app.post("/validator")
async def handle_validator(request: Request):
    ctx = propagate.extract(dict(request.headers))
    tracer = trace.get_tracer("validator_server")
    
    task = await request.json()
    skill_id = task.get("skill_id")
    input_data = task.get("input", {})
    print(f"Validator received skill: {skill_id}")
    
    with tracer.start_as_current_span(f"agent_server.validator.{skill_id}", context=ctx) as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("a2a.skill_id", skill_id)
        try:
            if skill_id in ["run_validation_and_classification", "validate_completeness", "classify_line"]:
                result = await run_validation_and_classification(input_data["parsed_data"])
                span.set_status(Status(StatusCode.OK))
                return result
            span.set_status(Status(StatusCode.ERROR, f"Unknown skill: {skill_id}"))
            return {"error": f"Skill {skill_id} not implemented for Validator"}
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            return {"error": str(e)}


@app.post("/router")
async def handle_router(request: Request):
    ctx = propagate.extract(dict(request.headers))
    tracer = trace.get_tracer("router_server")
    
    task = await request.json()
    skill_id = task.get("skill_id")
    input_data = task.get("input", {})
    print(f"Router received skill: {skill_id}")
    
    with tracer.start_as_current_span(f"agent_server.router.{skill_id}", context=ctx) as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("a2a.skill_id", skill_id)
        try:
            if skill_id in ["run_routing_and_summary", "route_submission", "generate_summary"]:
                result = await run_routing_and_summary(
                    parsed_data=input_data["parsed_data"],
                    line_of_business=input_data["line_of_business"],
                    validation_result=input_data["validation_result"],
                    user_profile=input_data["user_profile"],
                    submission_id=input_data.get("submission_id", "Unknown")
                )
                span.set_status(Status(StatusCode.OK))
                return result
            span.set_status(Status(StatusCode.ERROR, f"Unknown skill: {skill_id}"))
            return {"error": f"Skill {skill_id} not implemented for Router"}
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--agent", type=str, required=True)
    args = parser.parse_args()
    
    AGENT_NAME = args.agent
    print(f"Starting server for agent: {AGENT_NAME} on port {args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)
