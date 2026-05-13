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
tracer = trace.get_tracer("document_parser")
MODEL_NAME = os.getenv("PARSER_MODEL", os.getenv("LLM_MODEL", "gemini-1.5-flash"))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOCUMENT_TYPE_MAP = {
    "application": "application",
    "fleet_schedule": "fleet_schedule",
    "loss_history": "loss_history",
    "property_schedule": "property_schedule",
    "building_details": "building_details",
    "revenue_info": "revenue_info",
    "operations_description": "operations_description"
}

def load_document(file_path: str) -> dict:
    with open(file_path, "r") as f:
        return json.load(f)

def get_document_type(file_path: str) -> str:
    filename = os.path.basename(file_path).replace(".json", "")
    return DOCUMENT_TYPE_MAP.get(filename, "unknown")

async def extract_fields(document_content: dict, document_type: str) -> dict:
    prompt = pm.get_prompt("document_extraction", "v1", {
        "document_type": document_type,
        "document_content": json.dumps(document_content, indent=2)
    })
    submission_id = document_content.get("submission_id", "unknown")

    with tracer.start_as_current_span("parser.extract_fields") as span:
        attach_intake_semantics(span, "document_parser")
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("document_type", document_type)
        span.set_attribute("submission_id", submission_id)
        span.set_attribute("llm.model_name", MODEL_NAME)
        span.set_attribute("llm.prompt_template", "document_extraction_v1")
        # OpenInference message format for Arize AX Input/Output display
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
        # OpenInference message format for Arize AX Output display
        span.set_attribute("llm.output_messages.0.message.role", "assistant")
        span.set_attribute("llm.output_messages.0.message.content", raw[:4000])

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()
        try:
            result = json.loads(raw)
        except:
            result = {"document_type": document_type, "submission_id": submission_id,
                      "extracted_fields": document_content, "confidence": 0.7, "notes": "Parse error"}

        span.set_attribute("llm.token_count.prompt",
            getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0)
        span.set_attribute("llm.token_count.completion",
            getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0)
        span.set_status(Status(StatusCode.OK))
        return result

async def parse_document_async(file_path: str) -> dict:
    document_content = load_document(file_path)
    document_type = get_document_type(file_path)
    return await extract_fields(document_content, document_type)

async def parse_all_documents_parallel(submission_id: str) -> list:
    folder_path = os.path.join(BASE_DIR, f"data/submissions/{submission_id}")
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Submission folder not found: {folder_path}")
    doc_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".json")]
    tasks = [parse_document_async(fp) for fp in doc_files]
    results = await asyncio.gather(*tasks)
    return list(results)

async def parse_submission(submission_id: str) -> list:
    return await parse_all_documents_parallel(submission_id)
