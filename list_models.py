import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

print("Current configured model:", os.getenv("LLM_MODEL"))
print("\nSearching for llama-3.1-8b models...")
models = client.models.list()
for m in models.data:
    if "llama-3.1-8b" in m.id:
        print(m.id)


