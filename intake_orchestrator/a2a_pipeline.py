"""Sequential HTTP A2A calls: orchestrator → parser → validator → router (each remote process)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client_factory import ClientFactory
from a2a.client.client import ClientConfig
from a2a.types import AgentCard
from a2a.types import DataPart
from a2a.types import Message
from a2a.types import Part
from a2a.types import Role
from a2a.types import Task
from a2a.types import TaskState
from a2a.types import TextPart
from a2a.types import TransportProtocol

from google.adk.a2a.converters.part_converter import A2A_DATA_PART_METADATA_TYPE_FUNCTION_RESPONSE
from google.adk.a2a.converters.utils import _get_adk_metadata_key

from tracing.arize_setup import get_tracer

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _insured_name_from_parsed(parsed_data: list) -> str:
    for doc in parsed_data or []:
        if not isinstance(doc, dict):
            continue
        fields = doc.get("extracted_fields") or doc.get("extractedFields") or {}
        if isinstance(fields, dict):
            name = fields.get("insured_name")
            if name:
                return str(name)
    return "Unknown"


def _write_processed_json(
    sid: str,
    parsed_data: list,
    classification: Any,
    vinner: dict,
    routing: dict,
    summary: str,
) -> None:
    """Write data/processed/{sid}.json (used by script callers and legacy A2A path)."""
    processed_dir = os.path.join(_BASE_DIR, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)
    payload = {
        "submission_id": sid,
        "insured_name": _insured_name_from_parsed(parsed_data),
        "parsed_data": parsed_data,
        "classification": classification,
        "validation": vinner,
        "routing": routing,
        "summary": summary,
        "documents_processed": len(parsed_data),
        "processed_at": datetime.now().isoformat(),
        "status": "complete",
    }
    path = os.path.join(processed_dir, f"{sid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _materialize_candidate_to_processed(sid: str) -> None:
    """Promote data/processed_candidates/{sid}.json to data/processed/{sid}.json."""
    cand = os.path.join(_BASE_DIR, "data", "processed_candidates", f"{sid}.json")
    if not os.path.isfile(cand):
        raise RuntimeError(f"Expected candidate file missing: {cand}")
    with open(cand, encoding="utf-8") as f:
        data = json.load(f)
    data["processed_at"] = datetime.now().isoformat()
    data["status"] = "complete"
    out_dir = os.path.join(_BASE_DIR, "data", "processed")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{sid}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.remove(cand)


_META_TYPE = _get_adk_metadata_key("type")


def _unwrap_function_response_payload(data: dict[str, Any]) -> tuple[str | None, Any]:
    """Normalize ADK-encoded FunctionResponse in A2A DataPart.data."""
    name = data.get("name")
    resp = data.get("response")
    if resp is None:
        return name, None
    if isinstance(resp, dict):
        if "result" in resp:
            return name, resp["result"]
        if "output" in resp:
            return name, resp["output"]
    return name, resp


def _last_tool_outputs(task: Task) -> dict[str, Any]:
    """Last structured output per tool name from task history (agent messages)."""
    last: dict[str, Any] = {}
    for msg in task.history or []:
        if msg.role != Role.agent:
            continue
        for part in msg.parts:
            root = part.root
            if not isinstance(root, DataPart) or not root.metadata:
                continue
            if root.metadata.get(_META_TYPE) != A2A_DATA_PART_METADATA_TYPE_FUNCTION_RESPONSE:
                continue
            if not isinstance(root.data, dict):
                continue
            tool_name, out = _unwrap_function_response_payload(root.data)
            if tool_name:
                last[tool_name] = out
    return last


async def _fetch_agent_card(card_url: str, http: httpx.AsyncClient) -> AgentCard:
    parsed = urlparse(card_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rel = parsed.path
    if rel.startswith("/"):
        rel = rel[1:]
    resolver = A2ACardResolver(http, base_url=base)
    return await resolver.get_agent_card(relative_card_path=rel or None)


def _user_message(text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )


async def _invoke_specialist(
    *,
    card_url: str,
    instruction: str,
    http: httpx.AsyncClient,
    span_name: str,
    agent_label: str,
) -> Task:
    tracer = get_tracer("intake_orchestrator")
    with tracer.start_as_current_span(
        span_name,
        attributes={
            "openinference.span.kind": "CHAIN",
            "agent.name": agent_label,
            "intake.a2a": True,
            "intake.execution_mode": "sequential_a2a_http",
            "intake.trace.note": f"A2A message/send to specialist ({card_url}).",
        },
    ):
        card = await _fetch_agent_card(card_url, http)
        cfg = ClientConfig(
            httpx_client=http,
            streaming=False,
            polling=False,
            supported_transports=[TransportProtocol.jsonrpc, TransportProtocol.http_json],
        )
        factory = ClientFactory(cfg)
        client = factory.create(card)
        msg = _user_message(instruction)
        final: Task | None = None
        async for ev in client.send_message(request=msg):
            if isinstance(ev, tuple) and ev[0] is not None:
                final = ev[0]
            elif isinstance(ev, Task):
                final = ev
        if final is None:
            raise RuntimeError(f"No task returned from A2A agent at {card_url}")
        state = final.status.state if final.status else None
        if state == TaskState.failed:
            detail = ""
            if final.status and final.status.message and final.status.message.parts:
                detail = str(final.status.message.parts[0])
            raise RuntimeError(f"A2A task failed ({agent_label}): {detail or state}")
        return final


def _parsed_documents_from_parser_tools(outputs: dict[str, Any]) -> list:
    raw = outputs.get("extract_fields")
    if raw is None:
        raise RuntimeError(
            "document_parser did not return extract_fields tool output. "
            "Ensure the parser agent is running and the model invoked the tool."
        )
    if isinstance(raw, dict) and "documents" in raw:
        docs = raw["documents"]
        if isinstance(docs, list):
            return docs
    if isinstance(raw, list):
        return raw
    raise RuntimeError(f"Unexpected extract_fields payload type: {type(raw)}")


def _validation_bundle_from_validator_tools(outputs: dict[str, Any]) -> dict[str, Any]:
    cls = outputs.get("classify_line_of_business")
    val = outputs.get("validate_completeness")
    if cls is None or val is None:
        raise RuntimeError(
            "validator did not return classify_line_of_business and/or validate_completeness. "
            "Ensure the validator agent is running."
        )
    if not isinstance(cls, dict) or not isinstance(val, dict):
        raise RuntimeError("Validator tool outputs are not dicts.")
    line = cls.get("primary_line", "unknown")
    return {"classification": cls, "line_of_business": line, "validation": val}


async def run_sequential_a2a_intake(
    *,
    submission_id: str,
    user_role: str,
    parser_card_url: str,
    validator_card_url: str,
    router_card_url: str,
) -> dict[str, Any]:
    """
    Orchestrator-driven sequential A2A: parser → validator → router.
    Returns keys: parsed_data, classification, validation, routing, summary, documents_processed.
    """
    sid = submission_id.strip().upper()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(600.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    ) as http:
        # 1) Document parser agent
        p_task = await _invoke_specialist(
            card_url=parser_card_url,
            instruction=(
                f"You must call the extract_fields tool exactly once with "
                f'file_path="{sid}" and document_type="auto". '
                "Wait for the tool result before answering. After tools complete, reply in one short sentence."
            ),
            http=http,
            span_name="a2a.call_agent.document_parser",
            agent_label="document_parser",
        )
        p_out = _last_tool_outputs(p_task)
        parsed_data = _parsed_documents_from_parser_tools(p_out)
        raw_ex = p_out.get("extract_fields")
        staged_parsed = (
            raw_ex.get("parsed_data_staged_path")
            if isinstance(raw_ex, dict)
            else None
        )

        if staged_parsed:
            v_task = await _invoke_specialist(
                card_url=validator_card_url,
                instruction=(
                    "Call classify_and_validate_from_staged_file exactly once with "
                    f"staged_relative_path={json.dumps(staged_parsed)}. "
                    "Wait for the tool result. Then reply with one short sentence."
                ),
                http=http,
                span_name="a2a.call_agent.validator",
                agent_label="validator",
            )
            v_out = _last_tool_outputs(v_task)
            bundle = v_out.get("classify_and_validate_from_staged_file")
            if bundle is None or not isinstance(bundle, dict):
                raise RuntimeError(
                    "validator did not return classify_and_validate_from_staged_file. "
                    "Ensure validator/main.py is updated and running."
                )
            intake_staged = bundle.get("intake_payload_staged_path")
            line = bundle.get("line_of_business")
            vinner = bundle.get("validation")
            if not intake_staged or not line or not isinstance(vinner, dict):
                raise RuntimeError(f"Unexpected validator bundle: {bundle!r}")
            vc_cls = bundle.get("classification")
        else:
            parsed_json = json.dumps(parsed_data)
            v_task = await _invoke_specialist(
                card_url=validator_card_url,
                instruction=(
                    "You must run two tools in order using ONLY this parsed_data_json string "
                    f"(the full JSON array of documents, copy it exactly for both calls):\n{parsed_json}\n\n"
                    "1) Call classify_line_of_business(parsed_data_json=<that exact string>).\n"
                    "2) Call validate_completeness with the same parsed_data_json and line_of_business "
                    "equal to the primary_line string from step 1's result.\n"
                    "Use only tool outputs. One short sentence after both tools complete."
                ),
                http=http,
                span_name="a2a.call_agent.validator",
                agent_label="validator",
            )
            v_out = _last_tool_outputs(v_task)
            vc = _validation_bundle_from_validator_tools(v_out)
            line = vc["line_of_business"]
            vinner = vc["validation"]
            vc_cls = vc.get("classification")
            intake_staged = None
            if not isinstance(vinner, dict):
                raise RuntimeError("validate_completeness did not return a dict.")

        missing = vinner.get("missing_fields") or []
        if not isinstance(missing, list):
            missing = []
        completeness = float(vinner.get("completeness_score") or 0.0)
        missing_fields_str = json.dumps(missing)

        r1_task = await _invoke_specialist(
            card_url=router_card_url,
            instruction=(
                "Call the determine_routing tool exactly once. Arguments:\n"
                f"  line_of_business: {json.dumps(line)}\n"
                f"  completeness_score: {completeness}\n"
                f"  missing_fields_json: {repr(missing_fields_str)}\n"
                "(missing_fields_json is a string whose content is JSON for an array; "
                "use the repr value above verbatim as the third argument.)\n"
                "Then reply with one short sentence."
            ),
            http=http,
            span_name="a2a.call_agent.router.determine_routing",
            agent_label="router",
        )
        r1_out = _last_tool_outputs(r1_task)
        routing = r1_out.get("determine_routing")
        if routing is None or not isinstance(routing, dict):
            raise RuntimeError("router did not return determine_routing tool output.")

        routing_json_literal = json.dumps(routing)

        if intake_staged:
            r2_task = await _invoke_specialist(
                card_url=router_card_url,
                instruction=(
                    "Call finalize_intake_summary_from_staged exactly once with:\n"
                    f"  submission_id: {json.dumps(sid)}\n"
                    f"  user_role: {json.dumps(user_role)}\n"
                    f"  intake_payload_staged_relative_path: {json.dumps(intake_staged)}\n"
                    f"  routing_json: {json.dumps(routing_json_literal)}\n"
                    "Use routing_json exactly as the quoted string above (it is JSON for one object). "
                    "Then reply with one short sentence."
                ),
                http=http,
                span_name="a2a.call_agent.router.finalize_intake_summary",
                agent_label="router",
            )
            r2_out = _last_tool_outputs(r2_task)
            fin = r2_out.get("finalize_intake_summary_from_staged")
            if fin is None or not isinstance(fin, dict):
                raise RuntimeError("router did not return finalize_intake_summary_from_staged.")
            summary = str(fin.get("summary") or "")
            _materialize_candidate_to_processed(sid)
        else:
            all_data = {
                "parsed_data": parsed_data,
                "routing": routing,
                "validation": {
                    "classification": vc_cls,
                    "line_of_business": line,
                    **vinner,
                },
            }
            all_data_json = json.dumps(all_data, default=str)

            staging_dir = os.path.join(_BASE_DIR, "data", "a2a_staging")
            os.makedirs(staging_dir, exist_ok=True)
            staged_name = f"{sid}_{uuid.uuid4().hex}.json"
            staged_rel = f"data/a2a_staging/{staged_name}"
            staged_full = os.path.join(staging_dir, staged_name)
            with open(staged_full, "w", encoding="utf-8") as sf:
                sf.write(all_data_json)

            try:
                r2_task = await _invoke_specialist(
                    card_url=router_card_url,
                    instruction=(
                        "Call generate_intake_summary_from_staged_file exactly once with these arguments:\n"
                        f"  submission_id: {json.dumps(sid)}\n"
                        f"  user_role: {json.dumps(user_role)}\n"
                        f"  staged_relative_path: {json.dumps(staged_rel)}\n"
                        "Use the path string exactly as shown (forward slashes). "
                        "Then reply with one short sentence."
                    ),
                    http=http,
                    span_name="a2a.call_agent.router.generate_intake_summary",
                    agent_label="router",
                )
                r2_out = _last_tool_outputs(r2_task)
                summary_raw = r2_out.get("generate_intake_summary_from_staged_file")
                if summary_raw is None:
                    summary_raw = r2_out.get("generate_intake_summary")
                if summary_raw is None:
                    raise RuntimeError(
                        "router did not return generate_intake_summary_from_staged_file (or fallback "
                        "generate_intake_summary) tool output."
                    )
                if isinstance(summary_raw, dict):
                    summary = summary_raw.get("summary") or summary_raw.get("text") or json.dumps(summary_raw)
                else:
                    summary = str(summary_raw)
            finally:
                if os.path.isfile(staged_full):
                    try:
                        os.remove(staged_full)
                    except OSError:
                        pass

            _write_processed_json(sid, parsed_data, vc_cls, vinner, routing, summary)

        return {
            "parsed_data": parsed_data,
            "classification": vc_cls,
            "validation": vinner,
            "routing": routing,
            "summary": summary,
            "documents_processed": len(parsed_data),
        }
