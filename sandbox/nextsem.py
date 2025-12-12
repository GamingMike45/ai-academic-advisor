import sys
sys.path.append("../")
from core.llm import LLMAgent, INSTRUCTION_PROMPT, COURSE_RECOMMEND_SCHEMA
from core.tools import AdvisorTools
from core.helpers import *
import json
import os
import time

# tools = AdvisorTools()
transcript = json.loads(open("../aiadvisor/transcripts/2.json", "r").read())
# start = time.time()
# print(tools.transcript2context(transcript))
# end = time.time()
# print(f"Time taken: {(end - start)*1000} ms")


# # Next Semester, tool calls, no validation
# agent = LLMAgent(model_name="llama3.2",
#                  model_url="http://localhost:11434/api/chat",
#                  display_thinking=True)

# for line in agent("what is my name?", transcript):
#     print(line)

# # Next Semester, no tool calls, no validation
# messages = [
#     {"role": "system", "content": INSTRUCTION_PROMPT},
#     {"role": "system", "content": tools.transcript2context(transcript)},
#     {"role": "user", "content": "what is my name?"}
# ]
# out = agent.generate_response(messages=messages, use_tools=False)
# print(out)

# Next Semester, tool calls, validation
agent = LLMAgent(model_name="ministral-3:8b",
                 model_url="http://localhost:11434/api/chat",
                 display_thinking=True)

out = agent.next_semester(transcript, needed_credits=12, max_loop=25)
print(out)
