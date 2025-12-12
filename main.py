from core.llm import LLMAgent
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn
import json
import sqlite3
from pathlib import Path


app = FastAPI()

# Paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "core" / "courses.db"
TEMPLATES_PATH = BASE_DIR / "core" / "templates"

# Connect HTML templates and DB which live in core/
templates = Jinja2Templates(directory=str(TEMPLATES_PATH))

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    transcript: Optional[Dict[str, Any]] = None
    json_schema: Optional[Dict[str, Any]] = None

class GenerateRequest(BaseModel):
    query: str
    json_schema: Optional[Dict[str, Any]] = None

# display_thinking: Set to True to see the agent's thought process in the response
# Wanted a way to turn off thinking for final production use 
agent = LLMAgent(model_name="ministral-3:8b",
                 model_url="http://localhost:11434/api/chat",
                 display_thinking=True)

@app.get("/")
def read_root():
    return {"status": "agent is running!"}

def encode_stream(generator):
    """Helper to encode string tokens to bytes for StreamingResponse"""
    for token in generator:
        if token:
            yield token.encode('utf-8', errors='replace')

@app.post("/chat")
def chat(req: ChatRequest):
    return StreamingResponse(encode_stream(agent(req.messages,
                                                req.transcript)),
                                                media_type="text/plain; charset=utf-8")

@app.post("/generate")
def generate(req: GenerateRequest):
    return StreamingResponse(encode_stream(agent.generate_response(req.query)), 
                                                     media_type="text/plain; charset=utf-8")


# Helper function to fetch the courses from courses.db
def fetch_courses():
    # Connect the SQLite DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Execute query
    cursor.execute("SELECT * FROM courses")
    rows = cursor.fetchall()

    # This is the list we'll send to the endpoint
    courses = []
    for row in rows:
        courses.append({
            "course_code": row["course_code"],
            "expr": row["expr"],
            "valid": row["valid"],
            "not_found": json.loads(row["not_found"]) if row["not_found"] else []
        })

    conn.close()
    return courses

def fetch_course(course_code: str):
    """Fetch a single course from the DB"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM courses WHERE course_code = ?", (course_code,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "course_code": row["course_code"],
        "expr": row["expr"],
        "valid": row["valid"],
        "not_found": json.loads(row["not_found"]) if row["not_found"] else []
    }


def update_course_in_db(course_code: str, expr: str, valid: bool, not_found_list):
    """Update a single course row in the DB"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE courses SET expr = ?, valid = ?, not_found = ? WHERE course_code = ?",
        (expr, valid, json.dumps(not_found_list), course_code),
    )

    conn.commit()
    conn.close()

# Visit this URL to see the courses in courses.db
@app.get("/prerequisites", response_class=HTMLResponse)
def prerequisites(request: Request):
    courses = fetch_courses()
    return templates.TemplateResponse("prerequisites.html", {"request": request, "courses": courses})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

@app.get("/courses/{course_code}/edit", response_class=HTMLResponse)
def edit_course(request: Request, course_code: str):
    course = fetch_course(course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Convenience string for the text field
    not_found_str = ", ".join(course["not_found"]) if course["not_found"] else ""

    return templates.TemplateResponse(
        "edit_course.html",
        {
            "request": request,
            "course": course,
            "not_found_str": not_found_str,
        },
    )


@app.post("/courses/{course_code}/edit")
def update_course(
    course_code: str,
    expr: str = Form(""),
    valid: bool = Form(False),
    not_found: str = Form(""),
):
    # Turn comma-separated text into a list
    not_found_list = [s.strip() for s in not_found.split(",") if s.strip()]

    update_course_in_db(course_code, expr, valid, not_found_list)

    # Redirect back to the table view
    return RedirectResponse(url="/prerequisites", status_code=303)

