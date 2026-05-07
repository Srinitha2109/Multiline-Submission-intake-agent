import json
import os
import asyncio
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prompts.prompt_manager import PromptManager
from agents.llm_client import llm_client as model

load_dotenv()
tracer = trace.get_tracer("validator")
pm = PromptManager()
MODEL_NAME = os.getenv("VALIDATOR_MODEL", os.getenv("LLM_MODEL", "gemini-1.5-pro"))


REQUIRED_FIELDS = {
    "commercial_auto": ["vehicle_count", "fleet_schedule", "driver_list", "loss_history", "radius_of_operation"],
    "commercial_property": ["building_values", "construction_type", "occupancy", "square_footage", "protection_class"],
    "general_liability": ["industry_sic_code", "annual_revenue", "employee_count", "operations_description", "prior_claims"]
}

async def classify_line_of_business(parsed_data: list) -> dict:
    prompt = pm.get_prompt("lob_classification", "v1", {"parsed_data_json": json.dumps(parsed_data, indent=2)})
    
    with tracer.start_as_current_span("validator.classify_lob") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.model_name", MODEL_NAME)
        span.set_attribute("llm.prompt_template", "lob_classification_v1")
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
            return {"primary_line": "unknown", "confidence": 0.5, "reasoning": "Error parsing"}

async def validate_completeness(parsed_data: list, line_of_business: str) -> dict:
    required = REQUIRED_FIELDS.get(line_of_business, [])
    prompt = pm.get_prompt("completeness_validation", "v1", {
        "line_of_business": line_of_business,
        "parsed_data_json": json.dumps(parsed_data, indent=2),
        "required_fields_json": json.dumps(required, indent=2)
    })
    
    with tracer.start_as_current_span("validator.validate_completeness") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("line_of_business", line_of_business)
        span.set_attribute("llm.model_name", MODEL_NAME)
        span.set_attribute("llm.prompt_template", "completeness_validation_v1")
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
            return {"completeness_score": 0.5, "field_status": {}, "missing_fields": [], "validation_notes": "Error"}

async def run_validation_and_classification(parsed_data: list) -> dict:
    classification = await classify_line_of_business(parsed_data)
    line = classification.get("primary_line", "unknown")
    validation = await validate_completeness(parsed_data, line)
    return {"classification": classification, "line_of_business": line, "validation": validation}
