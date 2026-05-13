import json
import os
import asyncio
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prompts.prompt_manager import PromptManager
from agents.llm_client import llm_client as model
from tracing.pipeline_context import attach_intake_semantics

load_dotenv()
pm = PromptManager()
tracer = trace.get_tracer("router")
MODEL_NAME = os.getenv("ROUTER_MODEL", os.getenv("LLM_MODEL", "gemini-2.0-flash-exp"))

async def determine_routing(line_of_business: str, validation_result: dict) -> dict:
    prompt = pm.get_prompt("routing_decision", "v1", {
        "line_of_business": line_of_business,
        "completeness_score": str(validation_result.get("completeness_score", 0.0)),
        "missing_fields_json": json.dumps(validation_result.get("missing_fields", []))
    })
    
    with tracer.start_as_current_span("router.determine_routing") as span:
        attach_intake_semantics(span, "router")
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.model_name", MODEL_NAME)
        span.set_attribute("llm.prompt_template", "routing_decision_v1")
        span.set_attribute("input.value", prompt[:2000])
        span.set_attribute("llm.input_messages.0.message.role", "user")
        span.set_attribute("llm.input_messages.0.message.content", prompt[:4000])

        for attempt in range(3):
            try:
                response = await model.generate_content_async(prompt, model_name=MODEL_NAME)
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    raise e

        raw = response.text.strip()
        span.set_attribute("output.value", raw[:2000])
        span.set_attribute("llm.output_messages.0.message.role", "assistant")
        span.set_attribute("llm.output_messages.0.message.content", raw[:4000])
        
        span.set_attribute("llm.token_count.prompt",
            getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0)
        span.set_attribute("llm.token_count.completion",
            getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0)

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()
        try: 
            result = json.loads(raw)
            span.set_status(Status(StatusCode.OK))
            return result
        except: 
            span.set_status(Status(StatusCode.ERROR, "JSON parse error"))
            return {"queue": "Manual Review Queue", "priority": "high", "action_needed": "manual_review"}

async def generate_summary(parsed_data: list, routing_result: dict, user_profile: dict, submission_id: str = "Unknown", validation_result: dict = None) -> str:
    user_role = user_profile.get("role", "clerk")
    prompt = pm.get_prompt("intake_summary", "v1", {
        "submission_id": submission_id,
        "parsed_data_json": json.dumps(parsed_data, indent=2),
        "validation_result_json": json.dumps(validation_result or {}, indent=2),
        "routing_json": json.dumps(routing_result, indent=2),
        "user_role": user_role
    })
    
    with tracer.start_as_current_span("router.generate_summary") as span:
        attach_intake_semantics(span, "router")
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.model_name", MODEL_NAME)
        span.set_attribute("llm.prompt_template", "intake_summary_v1")
        span.set_attribute("input.value", prompt[:2000])
        span.set_attribute("llm.input_messages.0.message.role", "user")
        span.set_attribute("llm.input_messages.0.message.content", prompt[:4000])

        for attempt in range(3):
            try:
                response = await model.generate_content_async(prompt, model_name=MODEL_NAME)
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    raise e

        raw = response.text.strip()
        span.set_attribute("output.value", raw[:2000])
        span.set_attribute("llm.output_messages.0.message.role", "assistant")
        span.set_attribute("llm.output_messages.0.message.content", raw[:4000])
        
        span.set_attribute("llm.token_count.prompt",
            getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0)
        span.set_attribute("llm.token_count.completion",
            getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0)
        span.set_status(Status(StatusCode.OK))
        return raw

async def run_routing_and_summary(parsed_data: list, line_of_business: str, validation_result: dict, user_profile: dict, submission_id: str = "Unknown") -> dict:
    routing = await determine_routing(line_of_business, validation_result)
    summary = await generate_summary(parsed_data, routing, user_profile, submission_id, validation_result)
    return {"routing": routing, "summary": summary}
