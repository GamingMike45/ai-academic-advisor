from typing import Dict, Any, List, Optional

from torch._dynamo.bytecode_transformation import inst_has_op_bits
from core.tools import AdvisorTools
from core.helpers import *
import requests
import json
import re

class ChatHistoryManager:
    def __init__(self, filename: str = "data/chat_history.json"):
        self.filename = filename


    def save(self, history: List[Dict[str, str]]):
        try:
            with open(self.filename, "w", encoding="utf-8", errors="ignore") as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[ERROR] Failed to save chat history: {e}")


    def load(self) -> List[Dict[str, str]]:
        try:
            with open(self.filename, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
                if not text:
                    return []
                return json.loads(text)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []
        except Exception as e:
            print(f"[ERROR] Failed to load chat history: {e}")
            return []


    @staticmethod
    def extract_message_history(django_messages, user_id: int, limit: int = 20) -> List[Dict[str, str]]:
        """
        Extract and format message history from Django Message queryset.

        Args:
            django_messages: Django queryset or list of Message objects with role and content attributes
            user_id: User ID that all messages must belong to (REQUIRED for security)
            limit: Maximum number of messages to extract (default: 20 for 10 pairs)

        Returns:
            List of formatted messages ready for LLM: [{"role": "user"/"assistant", "content": "..."}]

        Raises:
            ValueError: If messages belong to different users or don't match provided user_id
        """
        # CRITICAL: Filter by user_id FIRST, then take last N messages
        # This ensures we get the full history for the user, not a mix of users
        filtered_messages = django_messages.filter(chat__user__id=user_id)

        # Fetch last N messages ordered by timestamp descending, then reverse for chronological order
        all_messages = list(filtered_messages.order_by('-timestamp')[:limit])
        all_messages = list(reversed(all_messages))

        # SECURITY VALIDATION: Double-check all messages belong to the specified user
        for msg in all_messages:
            msg_user_id = msg.chat.user.id if hasattr(msg, 'chat') else None
            # Should never happen, but just in case it SCREAMS SECURITY VIOLATION
            if msg_user_id != user_id:
                raise ValueError(f"SECURITY VIOLATION: Message {msg.message_id} belongs to user {msg_user_id}, not {user_id}")

        # Extract only user query and AI response content (between [AI RESPONSE] and [/AI RESPONSE])
        message_history = []
        for msg in all_messages:
            if msg.role == "User":
                # For user messages, just use the content
                message_history.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == "AI":
                # For AI messages, extract content between [AI RESPONSE] and [/AI RESPONSE]
                content = msg.content
                start_marker = "[AI RESPONSE]"
                end_marker = "[/AI RESPONSE]"

                start_idx = content.find(start_marker)
                end_idx = content.find(end_marker)

                if start_idx != -1 and end_idx != -1:
                    # Extract content between markers
                    extracted_content = content[start_idx + len(start_marker):end_idx].strip()
                    message_history.append({
                        "role": "assistant",
                        "content": extracted_content
                    })
                elif start_idx != -1:
                    # Only start marker found, take everything after it
                    extracted_content = content[start_idx + len(start_marker):].strip()
                    message_history.append({
                        "role": "assistant",
                        "content": extracted_content
                    })
                else:
                    # No markers found, use full content
                    message_history.append({
                        "role": "assistant",
                        "content": content
                    })

        return message_history

# TODO : PLAY WITH INSTRUCTION_PROMT
# Issue when asking What classes I should take next semester the tool call - get_inprogress_courses() - See current semester courses is the answer
INSTRUCTION_PROMPT = '''
You are a university academic advisor at Rowan University.

WORKFLOW:
1. Call the appropriate tool(s) to get the data you need
2. Provide a conversational answer based on the tool results

TOOL USAGE - CRITICAL:
- "What's in this major?" -> get_degree_courses()
- "Tell me about the major" -> get_degree_description()
- "Can I take [specific course]?" -> get_course_info(course="...") - PASS THE USER'S EXACT WORDS, don't try to guess course codes
- "What CS courses can I take?" -> search_courses(subject="CS", eligible_only=True)
- "Show me all 3-credit courses" -> search_courses(credits="3")
- "What machine learning courses exist?" -> search_courses(keyword="machine learning")

UNDERSTANDING COURSE STATUS:
- "IN PROGRESS" = Student is CURRENTLY TAKING these courses this semester
- "COMPLETED" = Student has finished with passing grade (C- or better)
- "NEEDS RETAKING" = Student took but got below C-, must retake
- "STILL NEEDED" = Student has NOT started yet

IMPORTANT RULES:
- For ANY question about what courses a student needs, ALWAYS use compare_degree_requirements()
- For IN PROGRESS courses, say "Once you complete [course name] which you're currently taking..."
- Only recommend courses from "STILL NEEDED" and "NEEDS RETAKING" sections
- Base your answer ONLY on the tool results - never guess or make assumptions
- Be conversational and friendly in your responses

CRITICAL - COURSE NAMING:
- ALWAYS include the full course title when mentioning ANY course code
- Format: "COURSE_CODE - Course Title" (e.g., "CS 04222 - Data Structures and Algorithms")
- NEVER say just "CS 04222" or "ADV 04434" without the title
- Students don't know what course codes mean - they need the titles!
- This applies to prerequisites, requirements, recommendations - EVERYTHING

PREREQUISITE HANDLING:
When displaying prerequisites to students, always include course titles alongside codes (e.g., "MATH 01210 - Calculus I").
If search_courses returns prerequisites as codes only and you need to show them in your answer, call get_course_info() to look up the titles first.
For large result sets, be selective and show 5-8 most relevant courses with full details
'''
# TODO: PLAY WITH TONE VOICE OF THE AI!


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

RECOMMEND_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "recommendation",
        "schema": {
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
    }
}

class LLMAgent:
    """
    LLM Agent for academic advising using OpenAI-style tool calling

    Attributes:
        instruction_prompt (str): The instruction prompt for the LLM
        model_url (str): The URL of the LLM endpoint
        model_name (str): The name of the LLM model
    """
    
    def __init__(self,
                 model_name: str = "llama3.1:8b",
                 model_url: str = "http://localhost:11434/api/chat",
                 instruction_prompt: str = INSTRUCTION_PROMPT,
                 chat_manager: Optional[ChatHistoryManager] = None,
                 display_thinking: bool = True,
                 temperature: float = 0.0, # Lower temperature for more deterministic responses
                 top_p: float = 0.9, # Nucleus sampling parameter
                 frequency_penalty: float = 0.0 # No penalty to allow repetition if needed
                 ): 

        self.instruction_prompt = instruction_prompt
        self.model_url = model_url
        self.model_name = model_name

        # LLM generation parameters for consistency
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty

        # Initialize all tools automatically from AdvisorTools
        self.tools = AdvisorTools()

        # Limit iterations to prevent infinite loops
        self.max_iterations = 8

        # Control whether thinking output is displayed to user
        self.display_thinking = display_thinking
        
        # Define tools in OpenAI format
        # TODO: ADD TOOLS TO LLM IN OPENAI FORMAT
        self.tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "next_semester",
                    "description": "Generate a response for the next semester, use this tool when ever there is a need to recommend courses",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "needed_credits": {
                                "type": "integer",
                                "description": "Number of credits the student wishes to take for the next semester"
                            }
                        },
                        "required": ["needed_credits"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_degree_courses",
                    "description": (
                        "Get raw list of ALL courses in a degree program (Rowan Core, major requirements, electives). "
                        "USE ONLY to see what's in a program catalog. DO NOT USE for 'what do I need' questions - use compare_degree_requirements() instead. "
                        "This tool shows the full catalog, not what the student specifically needs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degree": {
                                "type": "string",
                                "description": (
                                    "Optional: specific degree to look up. MUST be in full lowercase format with underscores. "
                                    "ALWAYS expand abbreviations: 'BS' -> 'bachelor_of_science', 'BA' -> 'bachelor_of_arts', 'BFA' -> 'bachelor_of_fine_arts'. "
                                    "Then add '_in_' followed by the major name in lowercase with underscores replacing spaces. "
                                    "Examples: 'bachelor_of_science_in_computer_science', 'bachelor_of_arts_in_history', 'bachelor_of_science_in_data_science'. "
                                    "If NOT provided, automatically uses student's current degree from transcript."
                                )
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_degree_description",
                    "description": (
                        "Get high-level overview of a degree program - what it's about, career paths, total credits needed. "
                        "Good for answering 'tell me about my major' questions. "
                        "Optionally specify a specific degree to look up a different degree than the student's current one."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degree": {
                                "type": "string",
                                "description": (
                                    "Optional: specific degree to look up. MUST be in full lowercase format with underscores. "
                                    "ALWAYS expand abbreviations: 'BS' -> 'bachelor_of_science', 'BA' -> 'bachelor_of_arts', 'BFA' -> 'bachelor_of_fine_arts'. "
                                    "Then add '_in_' followed by the major name in lowercase with underscores replacing spaces. "
                                    "Examples: 'bachelor_of_science_in_computer_science', 'bachelor_of_arts_in_history', 'bachelor_of_science_in_data_science'. "
                                    "If not provided, uses the student's current degree from their transcript."
                                )
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_course_info",
                    "description": (
                        "Get detailed information about a specific course including title, credits, description, and prerequisites. "
                        "Automatically checks if the student has met all prerequisites by comparing against their transcript. "
                        "Use this when a student asks about a specific course or wants to know if they can take a course."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "course": {
                                "type": "string",
                                "description": (
                                    "Course identifier - accepts EITHER course code OR course title. "
                                    "Examples: 'MATH 01230', 'Calculus III', 'Calculus 3', 'calc 3', 'Data Mining'. "
                                    "The tool will automatically search by code first, then by fuzzy title matching with Roman numeral normalization."
                                )
                            }
                        },
                        "required": ["course"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_courses",
                    "description": (
                        "Search for multiple courses by various criteria. "
                        "Use this when student asks about discovering courses like 'What CS courses can I take?', 'Show me all 3-credit electives', 'What data science courses are available?'. "
                        "Returns a list of matching courses with details. "
                        "NOTE: Prerequisites are returned as course codes only - you MUST use get_course_info() to look up prerequisite titles before displaying them to students."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subject": {
                                "type": "string",
                                "description": (
                                    "Filter by subject code (e.g., 'CS' for Computer Science, 'MATH' for Mathematics, 'STAT' for Statistics). "
                                    "Use uppercase subject codes."
                                )
                            },
                            "eligible_only": {
                                "type": "boolean",
                                "description": (
                                    "If true, only show courses student has met prerequisites for. "
                                    "Use this when student asks 'What CS courses CAN I TAKE?' vs 'What CS courses exist?'"
                                )
                            },
                            "credits": {
                                "type": "string",
                                "description": "Filter by credit count (e.g., '3' for 3-credit courses, '4' for 4-credit courses)"
                            },
                            "keyword": {
                                "type": "string",
                                "description": "Search keyword in course titles and descriptions (e.g., 'machine learning', 'database', 'algorithm')"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 20)"
                            }
                        },
                        "required": []
                    }
                }
            }]


    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], transcript: Dict[str, Any]) -> str:
        '''
        Execute a tool by name and return its results.

        This is the main dispatcher that routes tool calls to their implementations.
        Called by the agentic loop when the LLM requests a tool.

        Args:
            tool_name (str): Name of the tool to execute
            arguments (Dict[str, Any]): Tool-specific arguments from LLM
            transcript (Dict[str, Any]): Student's full transcript data

        Returns:
            str: Tool output as formatted text, or error message if tool not found
        '''
        # Data retrieval tools
        # TODO: ADD MORE TOOLS AS NEEDED
        if tool_name == "next_semester":
                print("Executing tool: next_semester")
                recommendation = self.next_semester(transcript, arguments.get("needed_credits"))

                if isinstance(recommendation, str):
                    return recommendation

                assert isinstance(recommendation, dict), "Recommendation is not a dictionary"

                out = []
                for course in recommendation['courses']:
                    course = re.search(self.tools.preqtester.course_pattern, course)
                    if not course:
                        print(f"Invalid course format: {course}")
                        continue
                    course = course.group()
                    course = self.tools.preqtester.find_course(course)
                    out.append(f"{course['CourseCode']} - {course['CourseTitle']} ({course['Credits']} credits)")
                return "\n".join(out)
        elif tool_name == "get_degree_courses":
            degree = arguments.get("degree")
            return self.tools.get_degree_courses(transcript, degree)
        elif tool_name == "get_degree_description":
            degree = arguments.get("degree")
            return self.tools.get_degree_description(transcript, degree)
        elif tool_name == "get_course_info":
            course = arguments.get("course")
            if not course:
                return "Error: course parameter is required"
            return self.tools.get_course_info(transcript, course)
        elif tool_name == "search_courses":
            subject = arguments.get("subject")
            eligible_only = arguments.get("eligible_only", False)
            credits = arguments.get("credits")
            keyword = arguments.get("keyword")
            max_results = arguments.get("max_results", 20)
            return self.tools.search_courses(transcript, subject, eligible_only, credits, keyword, max_results)
        else:
            return f"Error: Tool {tool_name} not found"


    def __call__(self, messages: List[Dict[str, str]], transcript: Optional[Dict[str, Any]] = None):

        if not transcript:
            yield "No transcript provided"
            return

        # DEBUG: Print message history being fed to LLM to terminal
        print(f"\n{'='*80}")
        print(f"[DEBUG] MESSAGE HISTORY RECEIVED FROM DJANGO ({len(messages)} messages)")
        print(f"{'='*80}")
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            print(f"{i}. [{role.upper()}]: {content}")
        print(f"{'='*80}\n")

        # Extract the latest query from messages (last user message)
        latest_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_query = msg.get("content", "")
                break

        # Initial thinking output
        if self.display_thinking:
            yield f"\n[THINKING]\n"
            yield f"Received {len(messages)} messages in history\n"
            yield f"Latest query: '{latest_query}'\n"
            yield f"Initializing conversation with system prompt, message history, and instruction\n"
            yield f"[/THINKING]\n"

        context = self.tools.transcript2context(transcript)

        # Initialize conversation with system message
        conversation_messages = [
            {"role": "system", "content": self.instruction_prompt},
            {"role": "system", "content": (
                "CRITICAL REMINDERS:\n"
                "1. When search_courses returns prerequisites as codes, you MUST call get_course_info() on each prereq code to get titles BEFORE giving your final answer\n"
                "2. NEVER display course codes without titles - students need full course names\n"
                "3. Be warm and conversational in your final response"
            )},
        ]

        # Add message history to conversation
        conversation_messages.extend(messages)
        conversation_messages.append({"role": "system", "content": context})
        conversation_messages.append({"role": "user", "content": latest_query})

        # Track executed tool calls to prevent duplicates
        executed_tools = {}

        # Iterative tool calling loop
        # Try up to max_iterations to get final answer currnetly self.max_iterations = 8
        for iteration in range(self.max_iterations):
            if self.display_thinking:
                yield f"\n[THINKING]\n"
                yield f"Starting iteration {iteration + 1}/{self.max_iterations}\n"
                yield f"Sending {len(conversation_messages)} messages to LLM for processing\n"
                yield f"[/THINKING]\n"

            try:
                # Make API call with tool definitions
                response = self.generate_response(conversation_messages, use_tools=True)
                response = response['message']

                print(response)

                if not response:
                    if self.display_thinking:
                        yield f"\n[THINKING]\n"
                        yield f"No response received from LLM - aborting\n"
                        yield f"[/THINKING]\n"
                    yield "Error: Failed to get response from LLM"
                    return

                # Check if LLM wants to use tools
                if response.get("tool_calls"):
                    tool_calls = response["tool_calls"]

                    if self.display_thinking:
                        yield f"\n[THINKING]\n"
                        yield f"LLM decided to call {len(tool_calls)} tool(s)\n"
                        tool_names = [tc["function"]["name"] for tc in tool_calls]
                        yield f"Tools requested: {', '.join(tool_names)}\n"
                        yield f"[/THINKING]\n"

                    # Add assistant message with tool calls to conversation
                    # Giving tools there own agent call for simplicity
                    conversation_messages.append({
                        "role": "assistant",
                        "content": response.get("content", ""),
                        "tool_calls": tool_calls
                    })

                    # Execute each tool call
                    for tool_call in tool_calls:
                        function_name = tool_call["function"]["name"]

                        if self.display_thinking:
                            yield f"\n[THINKING]\n"
                            yield f"Processing tool call: {function_name}\n"

                        function_args = tool_call["function"]["arguments"]
                        if self.display_thinking:
                            yield f"Parsed arguments: {function_args}\n"

                        # Create signature for deduplication
                        args_str = ",".join(f"{k}={v}" for k, v in sorted(function_args.items()))
                        signature = f"{function_name}({args_str})"

                        # Check if already executed
                        # Was my fix for Deepseek. Left it in
                        if signature in executed_tools:
                            if self.display_thinking:
                                yield f"Detected duplicate tool call - reusing cached result\n"
                                yield f"[/THINKING]\n"
                            result = executed_tools[signature]
                        else:
                            # Execute tool
                            if self.display_thinking:
                                yield f"Executing tool: {signature}\n"

                            result = self.execute_tool(function_name, function_args, transcript)
                            executed_tools[signature] = result

                            if self.display_thinking:
                                yield f"Tool execution complete, result cached\n"
                                yield f"[/THINKING]\n"
                                yield f"\n[TOOL RESULT: {function_name}]\n{result}\n[/TOOL RESULT]\n"
                                # DEBUG: Print to terminal
                                print(f"\n{'='*60}")
                                print(f"TOOL: {function_name}")
                                print(f"ARGS: {function_args}")
                                print(f"RESULT:")
                                print(result)
                                print(f"{'='*60}\n")

                        # Add tool response to conversation
                        # Generate tool_call_id if not provided by LLM (Ollama doesn't include it)
                        tool_call_id = tool_call.get("id", f"{function_name}_{iteration}")
                        conversation_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": function_name,
                            "content": result
                        })

                    # Continue loop to get final answer
                    # LLM will now decide whether to call more tools or provide final answer
                    # Trying to prevent infinite loops with max_iterations while allowing multiple tool calls over several iterations
                    # Still not sure it works
                    if self.display_thinking:
                        yield f"\n[THINKING]\n"
                        yield f"Tool results added to conversation, continuing to next iteration\n"
                        yield f"LLM can now choose to call more tools or provide final answer\n"
                        yield f"[/THINKING]\n"
                    continue

                else:
                    # No tool calls - LLM is providing final answer
                    content = response.get("content", "")

                    if content and content.strip():
                        if self.display_thinking:
                            yield f"\n[THINKING]\n"
                            yield f"LLM provided final answer\n"
                            yield f"Answer length: {len(content)} chars\n"
                            yield f"[/THINKING]\n"

                        # Stream the final answer
                        if self.display_thinking:
                            yield f"\n[AI RESPONSE]\n"

                        for char in content:
                            yield char

                        if self.display_thinking:
                            yield f"\n[/AI RESPONSE]\n"

                        return

                    # Empty content - this is an error
                    if self.display_thinking:
                        yield f"\n[THINKING]\n"
                        yield f"ERROR: LLM provided empty content\n"
                        yield f"[/THINKING]\n"

                    yield "I apologize, but I encountered an issue generating a response. Please try again."
                    return

            except Exception as e:
                # Catch-all for unexpected errors
                if self.display_thinking:
                    yield f"\n[THINKING]\n"
                    yield f"Exception caught during iteration {iteration + 1}: {e}\n"
                    yield f"[/THINKING]\n"
                yield f"Error: {str(e)}"
                return

        # Max iterations reached
        # If we exit the loop, it means we hit max iterations without a final answer
        if self.display_thinking:
            yield f"\n[THINKING]\n"
            yield f"Max iterations ({self.max_iterations}) reached without final answer\n"
            yield f"Executed tools: {list(executed_tools.keys())}\n"
            yield f"[/THINKING]\n"
        yield "I've gathered information but need to simplify. Please ask a more specific question."

    def generate_response(self, messages: List[Dict[str, Any]], 
                                schema: Optional[Dict[str, Any]] = None,
                                use_tools: bool = False) -> Optional[Dict[str, Any]]:
        '''
        Make API call to LLM with tool definitions.

        Args:
            messages (List[Dict[str, Any]]): Conversation messages
            schema (Optional[Dict[str, Any]]): forces JSON schema for response
        Returns:
            Optional[Dict[str, Any]]: Response from LLM with content and/or tool_calls
        '''
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty
        }

        if use_tools:
            payload["tools"] = self.tool_definitions

        # Add json schema if `schema` is provided
        if schema:
            print(f"generating a response with schema...")
            payload["format"] = schema

        try:
            response = requests.post(
                self.model_url,
                headers={"Content-Type": "application/json"},
                json=payload
            )

            if not response.ok:
                raise Exception(f"Request failed with status code {response.status_code}")

            result = response.json()

            return result

        except requests.exceptions.ConnectionError:
            raise ConnectionError("Failed to connect to the LLM API")
        except requests.exceptions.Timeout:
            raise TimeoutError("Request to LLM API timed out")
        except Exception:
            raise Exception("An unexpected error occurred")


    def next_semester(self, transcript: Dict[str, Any], needed_credits: int, max_loop: int = 5) -> Dict[str, Any]:
        '''
        Generate a response for the next semester.

        Args:
            transcript (Dict[str, Any]): Student's full transcript data
            needed_credits (int): Number of credits needed for the next semester
            max_loop (int): Maximum number of times to loop through the process
        Returns:
            Dict[str, Any]: Next semester data
        '''
        credits_left = 120 - transcript['earned_credits'] 

        if needed_credits > credits_left:
            return f"You requested {needed_credits} credits, but you have only {credits_left} credits left to complete your degree."

        # Initialize conversation with system message
        context = self.tools.transcript2context(transcript)

        messages = [
            {"role": "system", "content": INSTRUCTION_PROMPT},
            {"role": "system", "content": context},
        ]

        recommend_prompt = ("What courses do you recommend for the next semester? " +
                            "Place your recommendation between <recommendation> tags. ex. some text ... <recommendation> ONLY YOUR LIST OF RECOMMENDED COURSES </recommendation> ... some text")

        error_reason = ""
        for _ in range(max_loop):
            
            if error_reason:
                print(error_reason)
                messages.append({"role": "user", "content": error_reason})
            else:
                messages.append({"role": "user", "content": recommend_prompt})

            out = self.generate_response(messages)
            assistant_msg = out['message']['content']

            print("Assistant recommendation:", assistant_msg)

            try:
                out = self.tools.extract_recommendation_from_llm(assistant_msg)
                messages.append({"role": "assistant", "content": assistant_msg})
            except Exception as e:
                error_reason = f"Invalid response from LLM: {e}"
                continue
     
            if len(out['courses']) == 0:
                error_reason = "No courses recommended"
                continue
            
            valid, reason = self.tools.validate_courses(transcript, out['courses'], needed_credits)
            if valid:
                return out
            
            error_reason = (f"\nYou Recommended: {out['courses']}\n" +
                            f"Error: {reason}\n" +
                            "Create a new list of recommended courses based on the error\n\n")
        
        return "Agent exceeded max loop count with invalid recommendations"
