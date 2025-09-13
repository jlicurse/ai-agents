import os
from anthropic import Anthropic

client = Anthropic(api_key = os.environ.get("ANHTROPIC_API_KEY"))

resp = client.messages.create(
    model = "claude-opus-4-1-20250805",
    max_tokens=100,
    messages =[{"role": "user", "content": "Say hi in one sentence"}]
)

print(resp.content[0].text)