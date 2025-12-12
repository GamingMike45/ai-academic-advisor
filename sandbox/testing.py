import requests
import json

import sys
sys.path.append("../")

from core.tools import AdvisorTools
from core.llm import INSTRUCTION_PROMPT


tools = AdvisorTools()
transcript = json.loads(open("../aiadvisor/transcripts/2.json", "r").read())

url = "http://localhost:11434/api/chat"

COURSE_RECOMMEND_SCHEMA = {
    "type": "object",
    "properties": {
        "courses": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["courses"]
}

payload = {
    "model": "qwen3:4b",
    "messages": [
        {
            "role": "system",
            "content": INSTRUCTION_PROMPT
        },
        {
            "role": "system",
            "content": tools.transcript2context(transcript)
        },
        {
            "role": "user",
            "content": "What classes should I take next semester?"
        },
    ],
    "stream": False,
    "format": COURSE_RECOMMEND_SCHEMA
}

headers = {"Content-Type": "application/json"}

response = requests.post(url, headers=headers, json=payload)

if not response.ok:
    raise Exception(f"Request failed with status code {response.status_code}")

result = json.loads(response.json()['message']['content'])
print(result)

