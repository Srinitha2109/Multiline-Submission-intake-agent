import json
import uuid
import os
import httpx
import asyncio
from opentelemetry import trace, propagate
from opentelemetry.trace import Status, StatusCode

class A2AClient:
    def __init__(self, agent_card_path: str):
        with open(agent_card_path) as f:
            self.card = json.load(f)
        self.agent_name = self.card["name"]
        self.url = self.card["url"]

    async def send_task(
        self, skill_id: str, input_data: dict
    ) -> dict:
        task = {
            "id": str(uuid.uuid4()),
            "agent": self.agent_name,
            "skill_id": skill_id,
            "input": input_data,
            "status": "pending"
        }
        
        print(f"Sending task {skill_id} to {self.agent_name} at {self.url}...")
        
        # Inject W3C trace context so sub-agent spans link to the current trace
        headers = {}
        propagate.inject(headers)
        
        tracer = trace.get_tracer("a2a_client")
        with tracer.start_as_current_span(f"a2a.{self.agent_name}.{skill_id}") as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("a2a.agent", self.agent_name)
            span.set_attribute("a2a.skill_id", skill_id)
            span.set_attribute("a2a.url", self.url)
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url, 
                        json=task,
                        headers=headers,
                        timeout=60.0
                    )
                    if response.status_code == 200:
                        result = response.json()
                        task["status"] = "complete"
                        task["output"] = result
                        span.set_status(Status(StatusCode.OK))
                        return task
                    else:
                        error_msg = f"Agent returned status {response.status_code}: {response.text}"
                        span.set_status(Status(StatusCode.ERROR, error_msg))
                        return {
                            "status": "failed",
                            "error": error_msg
                        }
            except Exception as e:
                error_msg = f"Connection failed: {str(e)}"
                span.set_status(Status(StatusCode.ERROR, error_msg))
                span.record_exception(e)
                return {
                    "status": "error",
                    "error": error_msg
                }

    def get_agent_info(self) -> dict:
        return {
            "name": self.card["name"],
            "url": self.card["url"],
            "skills": [
                s["id"] for s in self.card["skills"]
            ]
        }
