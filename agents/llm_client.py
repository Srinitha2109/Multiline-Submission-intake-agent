import os
import asyncio
import json
from openai import AsyncOpenAI
import google.generativeai as genai
import vertexai
from vertexai.generative_models import GenerativeModel
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "google").lower()
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        
        if self.provider == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model_name)
        elif self.provider == "vertex":
            # Load project ID from credentials file if not in env
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            if not project_id and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                try:
                    with open(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"), "r") as f:
                        creds = json.load(f)
                        project_id = creds.get("project_id")
                except:
                    pass
            
            vertexai.init(project=project_id, location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
            self.client = GenerativeModel(self.model_name)
        else:
            self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1" if "openrouter" in self.provider else None,
                api_key=self.api_key,
            )

    async def generate_content_async(self, prompt: str, model_name: str = None):
        """
        Generates content from the configured LLM provider.
        """
        if self.provider == "google" or self.provider == "vertex":
            client = self.client
            if model_name and model_name != self.model_name:
                # Initialize a temporary client for the specific model
                if self.provider == "google":
                    client = genai.GenerativeModel(model_name)
                else:
                    client = GenerativeModel(model_name)
            
            response = await client.generate_content_async(prompt)
            return response
        else:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            
            class ResponseStub:
                def __init__(self, text, usage):
                    self.text = text
                    self.usage_metadata = usage
            
            class UsageStub:
                def __init__(self, prompt_tokens, completion_tokens):
                    self.prompt_token_count = prompt_tokens
                    self.candidates_token_count = completion_tokens

            usage = UsageStub(
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
            
            return ResponseStub(response.choices[0].message.content, usage)

# Singleton instance
llm_client = LLMClient()
