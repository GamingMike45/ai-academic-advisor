NOTE: THIS IS A COPY OF OUR PROJECT. THIS IS DUE TO SECURITY DUE TO USING LIVE STUDENT DATA TO OPTIMIZE THE PROJECT. 
LOOK AT CHANGE LOG IN README.MD FOR EACH PERSON'S CONTRIBUTIONS.

# AI Advisor

Team Members: Kyle Mains, David Chehet, Michael Perez Fenescey, Edwin Rodriguez, Tarosh Gurramkonda

## Project Structure

`python: 3.12.12`

As project currently stands. Update as changes are made please.

```
+-- core/                    # Core backend logic
|   +-- llm.py              # LLM agent with OpenAI-style tool calling
|   +-- tools.py            # Academic advisor tools (get_student_info, get_courses, etc.)
|   +-- helpers.py          # Shared utility functions (transcript parsing, degree lookup)
|   +-- courses.py          # Course scraping from catalog
|   +-- programs.py         # Program/degree parsing
|   +-- embedding.py        # ChromaDB embedding and search
|   +-- preqtester.py       # Prerequisite validation
|   +-- vault/              # Persistent data (degree JSONs, embeddings)
|
+-- aiadvisor/              # Django web application
|   +-- aiadvisor/          # Django project settings
|   +-- website/            # Main Django app (views, models, forms)
|
|
+-- sandbox/                # Testing and experimentation
+-- main.py                 # CLI entry point for testing LLM
+-- requirements.txt        # Dependencies (pip install -r requirements.txt)
```

### Key Files

| File            | Description                                                                          |
| --------------- | ------------------------------------------------------------------------------------ |
| `core/llm.py`   | LLM agent with iterative tool calling loop, streaming responses, and thinking output |
| `core/tools.py` | Tool implementations for data retrieval (student info, courses, degree requirements) |
| `main.py`       | CLI interface for testing the LLM agent with `display_thinking=ON/OFF`               |

## How to Start the Project

Follow these steps to get the project running:

### Step 1: Configure the LLM Model

In `main.py`, update the `LLMAgent` configuration to use your preferred model:

```python
agent = LLMAgent(
    model_name="mistral-small:24b",                              # Model name
    model_url="http://your-server:port/api/chat",          # Ollama OpenAI-compatible endpoint
    display_thinking=True                                  # Set to False for production (Broken now) Output is still displaying correct
)
```

### Step 2: Run Django Migrations

```
cd aiadvisor
python manage.py migrate
```

### Step 3: Start the FastAPI Server (LLM Backend)

```
python main.py
```

- Runs on: `http://localhost:8001`
- This handles all AI/LLM chat requests

### Step 4: Start the Django Website

Open a **second terminal** and run:

```
cd aiadvisor
python manage.py runserver
```

- Runs on: `http://localhost:8000`
- This is the main web interface

### Step 5: Access the Application

Open your browser and go to `http://localhost:8000` to use the AI Advisor.

> **Tip:** VS Code users can use the debugger (F5) with the preconfigured `launch.json` to start both servers simultaneously. (Tip from Michael)

## Change Log

### 2025-12-10 (Tarosh)
- fixed markdown rendering in chat.html
- found and fixed error with `next_semester` tool call blocking llm output

### 2025-12-10 (Tarosh)
- added a check for credits left in `validate_agent_courses`, if user asks for a recommendation with more credits than needed, it will says it cannot satisfy that request
- `validate_agent_courses` now returns a more meaningful reason for why it failed, when credits are too high or too low.
#### BIG CHANGE
structured output from ollama was creating a bottleneck for the llms critical thinking.
- removed structured output from `next_semester` function in `LLMAgent` class
- replaced it by requesting the model for placing recommendation in <recommendation></recommendation> tags
#### Model testing
- tested ministral-24b, and ministral-8b, these models seems to give the best output

### 2025-12-10 (Michael)
- **CRITICAL SECURITY FIX: Message history data leak vulnerability**  <- TG FOUND
  - Fixed bug in `ChatHistoryManager.extract_message_history()` where filtering happened AFTER limiting
  - Now filters by `user_id` FIRST, then takes last 20 messages (approximately 10 query pairs)
  - Added required `user_id` parameter to ensure explicit user filtering (not optional/ Required)
  - Implemented defense-in-depth security: ORM filtering -> ownership verification -> per-message validation (Just in case the `user_id` filter fails)
  - Added security checks to `clear_chat()` and `chat_page()` views ensuring users can only access/clear their own chat history

### 2025-12-09 (Michael)
- Adjusted instructions and tools prompt to work better with `mistral-small:24b` final LLM selected
- **Integrated Django message history with FastAPI for context-aware conversations**
  - Modified Django `send_message()` view to fetch last 10 message pairs (20 messages) from database
  - Enhanced `ChatHistoryManager` in `core/llm.py` with new `extract_message_history()` static method
  - Strips thinking blocks, tool results, and debug info from message history (extracts only content between `[AI RESPONSE]` and `[/AI RESPONSE]` markers) to prevent context bloat
  - Changed FastAPI `ChatRequest` class to accept `messages: List[Dict[str, str]]` instead of `query: str`
  - Updated `LLMAgent.__call__()` to accept message history and build conversation context
  - **Message Flow**: Django DB -> ChatHistoryManager.extract_message_history() -> FastAPI -> LLM with full context
- **Added comprehensive debugging for message history**
  - Terminal debug output shows all messages received from Django (in FastAPI server console)
  - Added `[HISTORY]` LIST OF PREVIOUSE QUERES `[/HISTORY]` thinking block to display conversation context in AI responses
  - Terminal output formatted with visual separators (80 and 60 character = dividers) for improved readability (Got tired of everthing getting squished together and not being readable for debug purposes)

### 2025-12-08 (Michael)

- Integrated `courses.db` prerequisite database with proper AND/OR logic for prerequisite checking
- Added prerequisite evaluation functions in `core/helpers.py`: `get_course_prerequisites()`, `evaluate_prerequisites()`, `parse_prerequisite_groups()`, `format_prerequisite_status()`
- Updated `get_course_info()` and `search_courses()` to use database for accurate prerequisite validation
- Added subject inference to course search (e.g., "calc" -> MATH) to prevent false matches
- Moved `normalize_degree_format()` to helpers, cleaned up duplicate functions
- Changed output format from `: HEADER :` to `[ HEADER ]` for better readability
- Added debug logging in `core/llm.py` to display full tool results in terminal

### 2025-12-04 (Edwin)
-Added export button that exports chat to a downloaded pdf

### 2025-12-04 (Tarosh)
- The big merge moving from LM Studio to Ollama (Merge branch 'tarosh' into lmstudio-2-ollama)
- `parse_degree_requirements_from_transcript` added to helpers
  - takes in degree and transcript as arguments
  - returns a dictionary of the degree requirements and the courses that are left to be taken
- `nextsem.py` in sandbox uses `parse_degree_requirements_from_transcript` and creates powerful context for LLM
- `next_semester` function in `LLMAgent` class now uses `parse_degree_requirements_from_transcript` to create powerful context for LLM


### 2025-12-02 (Tarosh)
- added `next_semester` function to `LLMAgent` class
- added `_validate_agent_courses` function
  - checks if recommendation 
    - meets credits neededs
    - meets preqs (`preqtester.py`)
    - doesn't recommend courses already taken
    - TODO: doesn't recommend courses already in progress
- missing classes context after failing prereq on agent recommendation
  - added a `find_min_courses` function to preqtester.py
  - added a `find_course` function to preqtester.py
- manually fixed cs degree file and `courses.json`, 
  - CS 04323 - Modern Software Development was null, now has 3 credits
  - CS 04305 - Web Programming was null, now has 3 credits
- tested the next_semester function with various models
- deepseek/deepseek-r1-0528-qwen3-8b throws AssertionError: total credits 0 is not a float

### 2025-12-02 (Michael)
- removed chromaDB
- added new course query tools
  - `get_course_info(course)` - Get detailed information about a specific course including title, credits, description, and prerequisites. Automatically checks if the student has met all prerequisites by comparing against their transcript. Accepts either course code (e.g., 'MATH 01230') or course title (e.g., 'Calculus III') with fuzzy matching and Roman numeral normalization
  - `search_courses(subject, eligible_only, credits, keyword, max_results)` - Search for multiple courses by various criteria. Use when students want to discover courses (e.g., 'What CS courses can I take?', 'Show me all 3-credit electives'). Can filter by subject code, eligibility (prerequisites met), credit count, and keywords. Returns a list of matching courses with details 
    - Note this assumes all classes in prereq are required. Needs to instead connect via TG database for the and/or courses

### 2025-12-01 (David)

- Fixed registration form missing `email` field. Fixed a bug where users would create an account but not be sent to the `dashboard`.
- Implemented drag-and-drop file upload for transcript PDFs, which was not working yesterday.
- Fixed dashboard semester statistics to calculate actual GPA and credits instead of using placeholder values
  - Created `semester_stats` dictionary in `views.py` that calculates GPA using standard 4.0 grade scale
  - Added custom template filter `get_item` in `templatetags/dashboard_filters.py` to access dictionary values in templates
  - Semester credits now correctly sum course credit hours, excluding withdrawn (W) and in-progress (IP) courses
- Transfer courses now display "Transfer Credit" instead of credit hours and show "N/A" for GPA
- Added styling for withdrawn courses - black badge with white "W" text, excluded from GPA calculations
- Fixed footer being cut off by sidebar - added CSS margin to push footer content right
- Adjusted chat page margins to prevent "Clear Chat" button from bleeding off screen edge

### 2025-11-30(David)

- Created `base.html` and `components.html` for getting a cleaner frontend look.
- Made all of our web pages look a lot better and be more interactive
- _Still need to:_ fix the upload transcript popup in `dashboard/`, and test for different bugs in the frontend experience.

### 2025-11-24(Edwin)

- Added an edit feature to David's db site
- Gives user/admin control over changing expression, validity, and adding to missing prereqs
- Remaining work: discuss with TG/team on how to move forward with validity

### 2025-11-23(David)

- Created a SQLite DB which stores all of Rowan's courses, along with their pre-requisites.
- Created a FastAPI endpoint `/prerequisites` to be able to view the new DB in the web.
- Run `uvicorn main:app --reload` from `root` to access website.
- Remaining work: create another endpoint to edit the courses and their pre-reqs. Also add functionality to filter through the courses with SQL in the web.

### 2025-11-23 (Michael)

- condesed files
  - `aiadvisor/website/helpers.py` into `core/helpers.py` Copy code deleted
- changed llm aritecture into using tools for data calling plus future tools
  - `get_student_info()` - Retrieves student's name, major, concentration, GPA, and total credits
  - `get_completed_courses(term)` - Shows all completed courses with grades, optionally filtered by term
  - `get_inprogress_courses()` - Displays current semester enrollment and workload
  - `get_degree_courses()` - Lists all required courses for the student's degree program
  - `get_degree_description()` - Provides overview of degree program, career paths, and total credits
- plased all llm tools in `core/tools.py` to keep `core/llm.py` lighter
- in `main` change display_thinking=ON/OFF True/False to see llm thinking for debug/final product purposes
- placed in max limit for tool calls `self.max_iterations = 4` from `core/llm.py`
- duplicate tool check forces llm to not recive that extra bloat
- Made `[AI RESPONSE]` ai answer `[/AI RESPONSE]` for easier reading of output
- Seperated think blokcs `[THINKING]` the thoughts of the machine `[/THINKING]`


### 2025-11-20 (Tarosh)
- testing parsing transcript and requirements
- fixed some issues with preq tester
- ideas to create a courses database, to manually fix or customize course preqs

### 2025-11-19 (Michael)

- updated code to use external llm server
- fix llm's not using utf-8 as output
- build degree json cleanup function for llm's in `core/helper.py`
- added better thinking blocks for easier reading of llm output
- merged mine and TG latest branches
- fixed transfer grade handling
  - grades now strip 'T' suffix before mapping (AT → A, BT → B)
- updated launch.json to start both FASTAPI and WEBSITE at once

### 2025-11-17 (Tarosh)

- updated transcript parser to pull info for students with multiple majors
- created dynamic pull of degrees
- added degree to file finder in core/helpers.py
- deleted transcript parser in core to remove unused and duplicated code
- .gitignore updated, and cleaned up

### 2025-11-18 (Kyle)

- Rebuilt settings page form
  - Now extends Django UserChangeForm
  - Only takes changes to username and password
- Updating a user now redirects to the login page

### 2025-11-13 (Tarosh)

- streaming tokens into django
- stripped css for readablity
- added clear messages option
- transcript saving and loading in django for the agent

### 2025-11-11 (Tarosh)

- created separate function for generating responses in llm.py
  - which allows for custom prompts, with any context, good for testing
- **call** function in llm.py now takes in a query, transcript, and stream to output a response for the student.
- added a new endpoint for generating responses with any custom prompt.

### 2025-11-05 (Tarosh)

- lowercase degree filenames was not tracked, but now it is!
- fastapi endpoint streaming in chat!

### 2025-11-04 (Tarosh)

- created sandbox folder to test things out
- scraped and created a departments_abbr.json that contains the abbreviations for departments
- scraped and created a subjects_abbr.json that contains the abbreviations for subjects
- embedding.py now has a ChromaDB class that handles embedding and searching degrees and courses
- changed all the degree files names to lowercase for ease of search!
- removed searching for degree file and hardcoded it to find the Bachelor of Science in Computer Science file
- removed searching for transcript and required transcript as a parameter
- added a way to get structured data from the model if needed with schema
- cleaned up context for the model, by manually extracting the relevant information from the transcript
- added streaming ability, so the tokens are printed as they are generated

### 2025-10-30 (David)

- Showing the GIT process.

### 2025-10-28 (Michael & Tarosh)

- AI branch merge
- Fixed merge conflics with programs.py
- Found out programs.py and courses.py are broken due to rowan website updates
- Sticking with seperated degrees files

### 2025-10-27 Transcript Upload & Dashboard Implementation, David

Implemented core transcript upload and dashboard functionality. Users can now upload their Rowan University transcript PDF, which is automatically parsed to extract academic information including major, minor, concentration, GPA, total credits, and all completed courses with grades. Created a dashboard view that conditionally displays either an upload form (for new users) or the parsed transcript data in a table format showing courses by term. Added support for transfer credits, in-progress courses, and re-upload functionality so users can update their transcripts. Integrated authentication requirements using `@login_required` decorator and added file validation (PDF format) with user feedback via Django messages. In-progress courses are marked with "IP" grade and stored separately from completed coursework.

**Known Issues**: GPA calculation is showing 3.539 instead of the expected 3.668 for myself, likely due to the parser missing some courses with complex titles (e.g., "MSTRPC FREN LIT ENGLISH TRANS"). The title pattern regex may need adjustment to capture all course title variations. I tried to fix the regex to include the 'Off-campus' classification that that course was but it didn't work. Keep in mind that in `website/helper.py` you will find the code from `transcript.py` in the `core` folder copied over. I did this to make imports easier for the helper functions, and to keep an original copy of the AI teams parser.

### 2025-10-27 (Tarosh)

- added a preq tester class to core/preqtester.py
- added a way to test preqs with a given set of taken courses to play.ipynb
- added ./core/vault/embeddinggemma-300m/ to .gitignore
  We are working to provide students with 24/7 access to academic advice.

Team Members: Kyle Mains, David Chehet, Michael Perez Fenescey, Edwin Rodriguez, Tarosh Gurramkonda, Clifford Mendoza-Castillo

### 2025-10-19, David

Django server is created in the `aiadvisor/` directory in the root of the project. Inside you will find another directory called `aiadvisor` which includes core Django, along with `website/` which is the specific Django application for our App. I have also created the Models, please read through them and let me know thoughts, I think they are good. I also created an Admin user. `Username: team, password: OurTeam!23`
Make sure to create a venv and run `pip install django`. After, you should be able to run `python3 manage.py runserver` and see 'Welcome to AI Advisor' at the root page, `home.html`

### 2025-10-20, David

Created `register.html` and `login.html` along with the required views and urls and forms to create those Users and save them into the database. After registering or logging in, you are redirected to `home.html` for now. To verify that the objects were created, you can run `python3 manage.py shell` in the aiadvisor/ directory. Then run `SELECT * FROM users;`. You will see that there is a `firstuser` created. `Password is Hello!23`.

### 2025-10-06 (Tarosh)

- process programs added to core/programs.py, helps parse the programs from the catalog.
- defaulted max_pages to 45 in core/courses.py, and added sleep to 0.25 seconds, for speeding up scraping.
- play.ipynb added, helps with testing and debugging.
  - created a function to parse the prerequisites from the course description.
  - a way to test preqs with a given set of taken courses.
