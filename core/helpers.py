from rapidfuzz import process
import json
import fitz
import re
import os
import sqlite3
from typing import Set, Tuple, List, Dict, Optional


# https://sites.rowan.edu/registrar/services-resources/grading-system-gpa.html
QUALITY_PTS = {
    'A': 4,
    'A-': 3.7,
    'B+': 3.3,
    'B': 3,
    'B-': 2.7,
    'C+': 2.3,
    'C': 2,
    'C-': 1.7,
    'D+': 1.3,
    'D': 1,
    'D-': 0.7,
    'F': 0
}

def has_passed(qual_pts: float, credits: float):
    # if credits is 0, then we know this class is passed
    if credits < 0.0001:
        return True
    
    # minimum C-
    return qual_pts / credits >= QUALITY_PTS['C-']

def get_completed_courses(transcript: dict):
    """
    Get a dictionary of completed courses. Drops courses that have lower than C-
    
    Args:
        transcript: The transcript dictionary
    
    Returns:
        A dictionary of completed courses
        {
            "course_code": {
                "title": "course_title",
                "credits": 4.0,
                "grade": "A"
            }
        }
    """
    GRADES = {
        "W": "withdrawn",
        "TR": "transfered"
    }
    completed = {}
    if 'transfer' in transcript:
        for course in transcript['transfer']:
            if float(course['credits']) > 0:
                completed[f"{course['subject']} {course['course_number']}"] = {
                    "title": course['title'],
                    "credits": float(course['credits']),
                    "grade": GRADES.get(course['grade'], course['grade'])
                }

    for term in transcript['completed']:
        for course in term['courses']:
            if has_passed(float(course['quality_points']), float(course['credits'])):
                completed[f"{course['subject']} {course['course_number']}"] = {
                    "title": course['title'],
                    "credits": float(course['credits']),
                    "grade": GRADES.get(course['grade'], course['grade'])
                }

    return completed

def degree2file(program: str, degree: str):
    """
    Convert a degree name to a file name.

    Args:
        program: The program name (Bachelor of Science, Master of Arts, etc.)
        degree: The degree name (Computer Science, Finance, etc.)
    """
    replacements = {
        "info" : "information",
        " ": "_",
        "&": "and",
    }
    # makes string regex safe, and joins with | (or)
    pattern = re.compile("|".join(map(re.escape, replacements)))
    # r'info|\ |\&'

    # replace all instances of keys with values
    full_string = f"{program.strip()} in {degree.strip()}".lower()
    filename_candidate = pattern.sub(lambda m: replacements[m.group(0)], full_string)
    
    files = os.listdir(os.path.join(os.path.dirname(__file__), "vault", "degrees"))
    
    return process.extract(filename_candidate, files)[0][0]


def pdf_to_text(pdf_path):
    doc = fitz.open(pdf_path)
    transcript = ""
    # Iterate through each page and extract text
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        transcript += page.get_text() + "\n"
    doc.close()
    return transcript

# currently works only on rowan transcripts from PDFS
def parse_transcript(data: str):
    """
    Extract student information from the data.

    Args:
        data (str): student information section in string.
    
    Returns:
        dict: The extracted student information.
    """

    student_info = {}

    name = re.findall(r"(?m)^Name[\s|\t|:]*?\r?\n(.*)", data)
    student_info["name"] = name[0] if name else None
    
    birth_date = re.findall(r"(?m)^Birth Date[\s|\t|:]*?\r?\n(.*)", data)
    student_info["birth_date"] = birth_date[0] if birth_date else None

    program = re.findall(r"(?m)^Program[\s|\t|:]*?\r?\n(.*)", data)
    student_info["program"] = ", ".join([m.split(",")[0].strip() for m in program]) if program else None
    
    major = re.findall(r"(?m)^Major and Department[\s|\t|:]*?\r?\n(.*)", data)
    student_info["major"] = ", ".join([m.split(",")[0].strip() for m in major]) if major else None
    
    concentration = re.findall(r"(?m)^Major Concentration[\s|\t|:]*?\r?\n(.*)", data)
    student_info["concentration"] = concentration[0] if concentration else None

    # must have these information
    assert name, "Name not found"
    assert birth_date, "Birth Date not found"
    assert student_info["program"], "Program not found"
    assert student_info["major"], "Major not found"

    assert len(program) == len(major), f"regex found programs: {program} \nmajors: {major}"

    return student_info

def extract_info(pdf_path, save=None):
    transcript = pdf_to_text(pdf_path)

    # get student info section
    sections = re.split(r'(?m)^(?=[A-Z][A-Z ]+$)', transcript)
    student_info_text = sections[1]

    # get student info
    student_info: dict = parse_transcript(student_info_text)

    # split by term
    term_pattern = r"(?i)((?:Fall|Spring|Summer|Winter) (?:[0-9]{4}))\n"
    blocks = re.split(term_pattern, transcript)

    # extract credits, quality points, gpa, etc.. from "Overall" section
    overalls = re.search(r"Overall:?\s*(.*?)(?=[A-Za-z]|$)", transcript, re.DOTALL)
    assert overalls, "Overall section not found"
    overalls = [float(x) for x in overalls.group(1).split("\n")[:6]]
    ampt_hrs, pasd_hrs, ernd_hrs, gpa_hrs, qual_pts, gpa = overalls
    student_info["attempted_credits"] = ampt_hrs
    student_info["passed_credits"] = pasd_hrs
    student_info["earned_credits"] = ernd_hrs
    student_info["gpa_credits"] = gpa_hrs
    student_info["quality_points"] = qual_pts
    student_info["gpa"] = gpa

    subj_ptrn = r"[A-Z]{2,4}" # Subject Code
    crse_ptrn = r"\d{5}" # Course Number
    cmps_ptrn = r"Main|Online|Off-campus" # Campus, Off-campus also exists, I added it in - David
    lvl_ptrn = r"UG|GR|[A-Z]{2}" # Level
    ttl_ptrn = r"[A-Z0-9\s\-/&:(),]+?" # Title - more specific pattern
    grde_ptrn = r"[A-Z]{1,2}[+-]?|W|TR" # Grade including W and TR
    crd_ptrn = r"\d+\.\d+" # Credits
    qual_ptrn = r"\d+\.\d+" # Quality Points


    # Pattern for transfer credits (no campus, level, or quality points)
    transfer_pattern = re.compile(r"(%s)\s+(%s)\s+(%s)\s+(%s)\s+(%s)" % 
                                (subj_ptrn, 
                                crse_ptrn, 
                                ttl_ptrn, 
                                grde_ptrn, 
                                crd_ptrn))

    # Pattern for completed courses
    course_pattern = re.compile(r"(%s)\s+(%s)\s+(%s)\s+(%s)\s+(%s)\s+(%s)\s+(%s)\s+(%s)" % 
                                (subj_ptrn, 
                                crse_ptrn, 
                                cmps_ptrn, 
                                lvl_ptrn, 
                                ttl_ptrn, 
                                grde_ptrn, 
                                crd_ptrn, 
                                qual_ptrn))

    # Pattern for in-progress courses (no grades, only credit hours)
    inprog_pattern = re.compile(r"(%s)\s+(%s)\s+(%s)\s+(%s)\s+(.+?)\s+(%s)(?=\s*(?:[A-Z]{2,4}\s+\d{5}|\s*$|\s*\w+\s*Transcript))" % 
                                (subj_ptrn, 
                                crse_ptrn, 
                                cmps_ptrn, 
                                lvl_ptrn, 
                                crd_ptrn), re.DOTALL)

    cur_term = None
    for i, block in enumerate(blocks):
        # found a term, the next block is the courses in that term
        match = re.match(r"(?i)(Fall|Spring|Summer|Winter) (\d{4})", block)
        if match and len(block) < 20:   
            cur_term = match.group(0)
            continue
        
        # found transfer credits
        if re.search(r"(?i)(?:TRANSFER CREDIT ACCEPTED BY INSTITUTION)", block):
            # init transfer courses list
            if "transfer" not in student_info:
                student_info["transfer"] = []

            # find all transfer courses and add them to list
            for match in re.finditer(transfer_pattern, block):
                title = re.sub(r'\s+', ' ', match.group(3)).strip()
                student_info["transfer"].append({
                    "subject": match.group(1),
                    "course_number": match.group(2),
                    "title": title,
                    "grade": match.group(4),
                    "credits": match.group(5)
                })
            continue

        # Check if this block contains in-progress courses (no grades, only credit hours)
        # For in-progress courses, the format is different - they have headers but no grades
        has_credit_hours_header = "Credit Hours" in block
        has_subject_course_header = "Subject" in block and "Course" in block
        
        # If it has the headers but no grades, it's likely in-progress
        if has_credit_hours_header and has_subject_course_header:
            # Use inprog_pattern to extract course information
            inprog_matches = list(re.finditer(inprog_pattern, block))
            if inprog_matches:
                # init inprogress courses list
                if "inprogress" not in student_info:
                    student_info["inprogress"] = [{
                        "term": cur_term,
                        "courses": []
                    }]
                elif student_info["inprogress"][-1]["term"] != cur_term:
                    student_info["inprogress"].append({
                        "term": cur_term,
                        "courses": []
                    })
                
                # Extract all in-progress courses from this block
                for match in inprog_matches:
                    # Clean up the title by removing extra whitespace and newlines
                    title = re.sub(r'\s+', ' ', match.group(5)).strip()
                    
                    student_info["inprogress"][-1]["courses"].append({
                        "subject": match.group(1),
                        "course_number": match.group(2),
                        "campus": match.group(3),
                        "level": match.group(4),
                        "title": title,
                        "credits": match.group(6)
                    })
                continue

        # rest should be completed credits
        for match in re.finditer(course_pattern, block):
            if "completed" not in student_info:
                student_info["completed"] = [{
                    "term": cur_term,
                    "courses": []
                }]
            elif student_info["completed"][-1]["term"] != cur_term:
                student_info["completed"].append({
                    "term": cur_term,
                    "courses": []
                })
            title = re.sub(r'\s+', ' ', match.group(5)).strip()
            student_info["completed"][-1]["courses"].append({
                "subject": match.group(1),
                "course_number": match.group(2),
                "campus": match.group(3),
                "level": match.group(4),
                "title": title,
                "grade": match.group(6),
                "credits": match.group(7),
                "quality_points": match.group(8)
            })
    
    if save:
        with open(save, "w") as f:
            json.dump(student_info, f, indent=4)
    
    return student_info

# david's work
def json_to_toon_robust(data, indent="    ", level=0):
    """
    Robust TOON converter that handles arbitrary JSON structures.
    Works with nested objects, arrays, and mixed types.
    This is to be used to convert JSON objects to TOON before sending
    the transcript object to the AI. By reducing the token count, we 
    allow for an optimized, faster AI experience.
    
    Args:
        data: Any JSON-serializable data structure
        indent: String to use for indenting (default: 4 spaces)
        level: Current nesting level (used internally)
    
    Returns:
        String in TOON format for the LLM
    """
    result = []
    current_indent = indent * level
    
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                # Empty array
                if len(value) == 0:
                    result.append(f"{current_indent}{key}[0]:")
                elif isinstance(value[0], dict):
                    # Array of objects
                    # Check if all objects have the same keys
                    first_keys = list(value[0].keys())
                    all_same = all(
                        isinstance(item, dict) and list(item.keys()) == first_keys
                        for item in value
                    )
                    
                    if all_same:
                        # Separate simple and nested fields
                        simple_fields = []
                        nested_fields = {}
                        
                        for field in first_keys:
                            sample_val = value[0][field]
                            if isinstance(sample_val, (list, dict)):
                                nested_fields[field] = sample_val
                            else:
                                simple_fields.append(field)
                        
                        # Write header and simple fields
                        count = len(value)
                        if simple_fields:
                            field_str = ", ".join(simple_fields)
                            result.append(f"{current_indent}{key}[{count}]{{{field_str}}}:")
                            
                            for item in value:
                                vals = [str(item.get(f, "")) for f in simple_fields]
                                result.append(f"{current_indent}{indent}{', '.join(vals)}")
                        else:
                            result.append(f"{current_indent}{key}[{count}]:")
                        
                        # Process nested fields for each item
                        if nested_fields:
                            for item in value:
                                for nfield in nested_fields.keys():
                                    nested_data = item.get(nfield)
                                    if nested_data is not None:
                                        nested_str = json_to_toon_robust(
                                            {nfield: nested_data},
                                            indent,
                                            level + 1
                                        )
                                        result.append(nested_str)
                    else:
                        # Objects with different structures
                        result.append(f"{current_indent}{key}[{len(value)}]:")
                        for item in value:
                            nested_str = json_to_toon_robust(item, indent, level + 1)
                            result.append(nested_str)
                
                elif isinstance(value[0], list):
                    # Array of arrays
                    result.append(f"{current_indent}{key}[{len(value)}]:")
                    for item in value:
                        nested_str = json_to_toon_robust(item, indent, level + 1)
                        result.append(nested_str)
                else:
                    # Array of primitives
                    result.append(f"{current_indent}{key}[{len(value)}]:")
                    for item in value:
                        result.append(f"{current_indent}{indent}{item}")
            
            elif isinstance(value, dict):
                # Nested object - FIX: Properly handle recursion 
                result.append(f"{current_indent}{key}:")
                nested_str = json_to_toon_robust(value, indent, level + 1)
                result.append(nested_str)
            
            else:
                # Simple key-value
                result.append(f"{current_indent}{key}: {value}")
    
    elif isinstance(data, list):
        # Top-level array (rare but possible)
        # Edge case
        if len(data) == 0:
            result.append(f"{current_indent}[0]:")
        elif isinstance(data[0], dict):
            first_keys = list(data[0].keys())
            all_same = all(isinstance(item, dict) and list(item.keys()) == first_keys for item in data)
            
            if all_same:
                field_str = ", ".join(first_keys)
                result.append(f"{current_indent}[{len(data)}]{{{field_str}}}:")
                for item in data:
                    vals = [str(item[f]) for f in first_keys]
                    result.append(f"{current_indent}{indent}{', '.join(vals)}")
            else:
                result.append(f"{current_indent}[{len(data)}]:")
                for item in data:
                    nested_str = json_to_toon_robust(item, indent, level + 1)
                    result.append(nested_str)
        else:
            result.append(f"{current_indent}[{len(data)}]:")
            for item in data:
                result.append(f"{current_indent}{indent}{item}")
    
    else:
        # Primitive value
        result.append(f"{current_indent}{data}")
    
    return "\n".join(result)

# Michael's work
def course_transformer_into_json(course_str):
    """
    Parse a course string into structured JSON.
    Examples:
      - 'CMS 04323 - Images of Athletes in Popular Culture Credits: 3'
      - 'HIST 05429 - Special Topics: History of Witchcraft'
    """
    pattern = r'^(?P<subject>[A-Z]{2,5})\s+(?P<course_number>\d{3,5})\s*-\s*(?P<title>.*?)(?:\s+Credits:\s*(?P<credits>\d+(?:\s*to\s*\d+)?))?$'
    match = re.match(pattern, course_str.strip())
    if match:
        subject = match.group("subject")
        course_number = match.group("course_number")
        title = match.group("title").strip()
        credits = match.group("credits")
        title = re.sub(r"\s*Credits:?\s*$", "", title).strip()
        # Handle cases like "3 to 6"
        if credits and "to" in credits:
            credits = credits.strip()
        elif credits:
            credits = int(credits)
        else:
            credits = None
        return {
            "subject": subject,
            "course_number": course_number,
            "title": title,
            "credits": credits
        }
    # fallback: text not matching the course pattern
    return {
        "subject": None,
        "course_number": None,
        "title": course_str.strip(),
        "credits": None
    }


def extract_courses_from_text(text):
    """
    - Extract course codes and details from free-form text
    - Usually matches patterns like 'CMS 04323 - Images of Athletes in Popular Culture Credits: 3'
    - Ment to handle multiple courses in a block of text especially when separated by newlines or commas or words.
    - Example can be found in any ROWAN CORE curriculum description.

    Args:
        text string containing course information. 

    Returns:
        List of course dicts with keys: subject, course_number, title, credits
    """

    # Regular expression to match course patterns
    pattern = r'([A-Z]{2,5})\s+(\d{3,5})\s+([A-Za-z\s\-&,/:()]+?)(?=\s+[A-Z]{2,5}\s+\d{3,5}|$)'
    matches = re.findall(pattern, text)
    
    # Build course list
    courses = []
    for match in matches:
        subject = match[0]
        course_number = match[1]
        title = match[2].strip()
        
        courses.append({
            "subject": subject,
            "course_number": course_number,
            "title": title,
            "credits": None
        })
    
    return courses


def extract_total_credits(content):
    """
    - Extract total credits required from the content
    - Look for headers indicating total required credits and extract the number.

    Args:
        content dict representing the content section of the degree JSON. 

    Returns:
        total credits as int or None if not found
    """
    # Search for total required credits in headers
    for header, value in content.items():
        # Check for total required credits pattern
        if "total required credits" in header.lower():
            match = re.search(r'(\d+)\s*s\.h\.', header)
            if match:
                return int(match.group(1))
            # Check in value if it's a dict or list
            if isinstance(value, dict):
                notes = value.get("notes", [])
                for note in notes:
                    if isinstance(note, str):
                        match = re.search(r'(\d+)\s*s\.h\.', note)
                        if match:
                            return int(match.group(1))
            # Check in value if it's a dict or list
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        match = re.search(r'(\d+)\s*s\.h\.', item)
                        if match:
                            return int(match.group(1))
    return None


def format_course_for_output(course):
    """
    - Format a course dictionary into a readable string for output
    - Returns None if course is invalid to avoid empty lines

    Args:
        course dict with keys 'subject', 'course_number', 'title', 'credits'
    
    Returns:
        Formatted string or None
    """
    # Validate course dict
    if not isinstance(course, dict):
        return None
    
    subject = course.get("subject")
    course_number = course.get("course_number")
    title = course.get("title")
    credits = course.get("credits")
    
    # Ensure required fields are present
    if not subject or not course_number:
        return None
    
    parts = [f"{subject} {course_number}"]
    
    # Add title and credits if available
    if title:
        parts.append(f"- {title}")
    # Should never reach here due to earlier validation but just in case
    else:
        parts.append("- (title not specified)")
    
    if credits:
        parts.append(f"({credits} credits)")
    # Some courses may not specify credits. Add placeholder.
    else: 
        parts.append("(credits not specified)")
    
    return " ".join(parts)

def parse_degree_requirements_from_transcript(degree:dict, transcript:dict):
    # TODO: Rowan Core and Rowan Experience needs to checked (currently will be completed for all)
    completed = get_completed_courses(transcript)
    courses_left = {}
    for head in degree['content'].keys():
        # find "11 s.h." or "32-33 s.h." in the section headings
        credits_needed = re.search(r'(\d{1,3})\s?-?\s?((\d{1,3}))?\s+s.h.', head)
        has_requirements = 'requirements' in degree['content'][head]

        # if required credits is in section heading, and it contains requirements (a.k.a courses) under heading
        if credits_needed and has_requirements:
            requirements = degree['content'][head]['requirements']
            
            # extract the required credits to complete this section
            _frst = credits_needed.group(1)
            _scnd = credits_needed.group(2)

            # if we find 11 s.h., this would be (11, 11) credits
            # if we find 11-12 s.h., this would be (11, 12) credits
            _frst = float(_frst)
            _scnd = float(_scnd) if _scnd else _frst

            # initalize to accumulate unfinished courses in the section
            courses_left[head] = {
                'total_credits': [_frst, _scnd],
                'completed': False,
                'completed_credits': 0,
                'not_completed': []
            }

            # each block is an "and" block or and "or" block of courses
            for block in requirements:
                # formats the courses in course codes to check with transcript course codes
                req_crses = {f"{crse['subject']} {crse['course_number']}":{
                                "title": crse['title'],
                                "credits": crse['credits'] } for crse in block['courses']}
                completed_crses = set(completed) & set(req_crses)     

                # if there is any completed course in the or block, then the block is satisfied 
                not_completed = []
                if block['type'] == 'or':
                    not_completed += [] if len(completed_crses) > 0 else req_crses 
                else:
                    not_completed += list(set(req_crses) - completed_crses)

                courses_left[head]['not_completed'] = {_c: req_crses[_c] for _c in not_completed}

                # accumulate completed credits
                courses_left[head]['completed_credits'] += sum([completed[crse]['credits'] for crse in completed_crses])

            # ensure that we have met the credits needed to complete this section
            if courses_left[head]['completed_credits'] >= _frst or courses_left[head]['completed_credits'] >= _scnd:
                courses_left[head]['completed'] = True

            # if there are no courses left to complete, then the section is completed
            if len(courses_left[head]['not_completed']) == 0:
                courses_left[head]['completed'] = True

    return courses_left


def parse_degree_requirements(json_filepath):
    # TODO: optimize this function, currently there are multiple passes over the data
    """
    Parse degree requirements from a structured JSON file and return formatted text output.
    
    Args:
        json_filepath: Path to the JSON file containing degree information
        
    Returns:
        Formatted string with degree requirements
    """

    data = open(json_filepath, 'r', encoding='utf-8').read()
    data = json.loads(data)
    
    output = []
    
    # Extract degree name (Turned OFf) 
    degree_name = data.get("name", "Unknown Degree")
    #output.append(f"Degree Name: {degree_name}")
    #output.append("")
    
    # Extract total credits from content first
    content = data.get("content", {})
    total_credits = extract_total_credits(content)
    
    # Output total credits at the top due to its importance
    if total_credits:
        output.append(f"Total Credits: {total_credits}")
        output.append("")
    
    # Extract description from first content section
    description = None
    for header, value in content.items():
        if isinstance(value, list) and value and degree_name.lower() in header.lower():
            description = value[0] if value else None
            break
    
    # Output description due to its importance
    if description:
        output.append(f"Description: {description}")
        output.append("")
    
    # TODO: manually add the rowan core, because it is the same for all rowan students
    # # Parse Rowan Core requirements
    # rowan_core_courses = []
    # for header, value in content.items():
    #     if "rowan core" in header.lower():
    #         # Extract courses from notes or list format
    #         if isinstance(value, dict) and "notes" in value:
    #             for note in value.get("notes", []):
    #                 courses = extract_courses_from_text(note)
    #                 rowan_core_courses.extend(courses)
    #         elif isinstance(value, list):
    #             for item in value:
    #                 if isinstance(item, str) and re.search(r"[A-Z]{2,5}\s+\d{3,5}", item):
    #                     courses = extract_courses_from_text(item)
    #                     rowan_core_courses.extend(courses)
    
    # # Output Rowan Core requirements due to its importance
    # if rowan_core_courses:
    #     output.append("Rowan Core Requirements:")
    #     for course in rowan_core_courses:
    #         formatted = format_course_for_output(course)
    #         if formatted:
    #             output.append(f"- {formatted}")
    #     output.append("")
    
    # Parse all required AND courses and OR course groups
    required_courses = []
    choice_groups = []
    restricted_electives = []
    restricted_credit_req = None
    
    for header, value in content.items():
        # Skip certain sections
        if any(skip in header.lower() for skip in ["rowan core", "rowan experience", "free elective", "total required"]):
            continue
        
        # Check if this is a restricted electives section
        is_restricted = "restricted elective" in header.lower() or "elective" in header.lower()
        
        # Extract credit requirement for restricted electives
        if is_restricted and not restricted_credit_req:
            match = re.search(r'(\d+)\s*s\.h\.', header)
            if match:
                restricted_credit_req = match.group(1)
        
        # Handle dict format sections
        if isinstance(value, dict) and "requirements" in value:
            requirements = value.get("requirements", [])
            
            for group in requirements:
                if not isinstance(group, dict) or "courses" not in group:
                    continue
                
                group_type = group.get("type", "and").lower()
                courses = group.get("courses", [])
                
                # Handle OR groups
                if group_type == "or":
                    # Filter out non-course entries
                    valid_courses = [c for c in courses if c.get("subject") and c.get("course_number")]
                    if valid_courses:
                        choice_groups.append(valid_courses)
                # Handle AND groups
                elif group_type == "and":
                    if is_restricted:
                        restricted_electives.extend(courses)
                    else:
                        required_courses.extend(courses)
        # Handle list format sections
        elif isinstance(value, list):
            # Handle list format sections that may contain AND/OR markers
            for item in value:
                if isinstance(item, str):
                    if item == "AND" or item == "OR":
                        continue
                    # Check if item is a formatted course
                    if re.search(r"[A-Z]{2,5}\s+\d{3,5}", item):
                        parsed = course_transformer_into_json(item)
                        if parsed.get("subject") and parsed.get("course_number"):
                            if is_restricted:
                                restricted_electives.append(parsed)
                            else:
                                required_courses.append(parsed)
    
    # Output required courses
    if required_courses:
        output.append("Required Courses:")
        for course in required_courses:
            formatted = format_course_for_output(course)
            if formatted:
                output.append(f"- {formatted}")
        output.append("")
    
    # Output choice groups
    for i, group in enumerate(choice_groups):
        if len(group) > 1:
            output.append("Choose One:")
            for course in group:
                formatted = format_course_for_output(course)
                if formatted:
                    output.append(f"- {formatted}")
            output.append("")
    
    # Output restricted electives
    if restricted_electives:
        if restricted_credit_req:
            output.append(f"Restricted Electives (Choose {restricted_credit_req} credits):")
        else:
            output.append("Restricted Electives:")
        
        for course in restricted_electives:
            formatted = format_course_for_output(course)
            if formatted:
                output.append(f"- {formatted}")
        output.append("")
    
    return "\n".join(output)


def normalize_course_code(code: str) -> str:
    """
    Normalize course code for comparison.
    Converts "CS 04103", "CS04103", "cs 04103" all to "CS04103"
    """
    # Remove spaces and convert to uppercase
    # reduce to simplify information in llm
    normalized = code.replace(" ", "").upper()
    return normalized


def normalize_degree_format(degree_str: str) -> Optional[str]:
    """
    Convert various degree name formats to the required lowercase underscore format.
    Always converts to lowercase first.

    Examples:
        "Bachelor of Science in Data Science" -> "bachelor_of_science_in_data_science"
        "BS in Data Science" -> "bachelor_of_science_in_data_science"
        "BS Data Science" -> "bachelor_of_science_in_data_science"
    """
    # Force to lowercase first
    normalized = degree_str.lower().strip()

    # Skip if it's a URL - return None to indicate error
    if normalized.startswith("http") or normalized.startswith("www"):
        return None

    # If already in correct format (lowercase with underscores, no spaces), return as-is
    if "_" in normalized and " " not in normalized:
        return normalized

    # Expand common abbreviations
    abbreviations = {
        "bs": "bachelor_of_science",
        "ba": "bachelor_of_arts",
        "bfa": "bachelor_of_fine_arts",
        "b.s.": "bachelor_of_science",
        "b.a.": "bachelor_of_arts",
        "b.f.a.": "bachelor_of_fine_arts"
    }

    # Check if starts with abbreviation
    for abbr, full in abbreviations.items():
        if normalized.startswith(abbr + " in "):
            # e.g., "bs in data science" -> "bachelor_of_science in data science"
            normalized = full + "_in_" + normalized[len(abbr) + 4:]
            break
        elif normalized.startswith(abbr + " "):
            # e.g., "bs data science" -> "bachelor_of_science in data science"
            normalized = full + "_in_" + normalized[len(abbr) + 1:]
            break

    # Replace remaining spaces with underscores
    normalized = normalized.replace(" ", "_")

    # Remove multiple underscores
    while "__" in normalized:
        normalized = normalized.replace("__", "_")

    return normalized


def is_passing_grade(grade: str) -> bool:
        """
        Check if a grade is C- or better (passing).
        Returns False for D+, D, D-, F, or W
        """
        grade = grade.strip().upper()

        # Failing grades
        failing_grades = ['D+', 'D', 'D-', 'F', 'W', 'WITHDRAWN']

        if grade in failing_grades:
            return False

        return True


def normalize_course_title_for_search(title: str) -> str:
    """
    Normalize course title for fuzzy searching.
    Converts Roman numerals to numbers, lowercases, and standardizes spacing.

    Examples:
        "Calculus III" -> "calculus 3"
        "Chemistry I" -> "chemistry 1"
        "Physics II" -> "physics 2"
    """
    # Convert to lowercase
    normalized = title.lower().strip()

    # Replace Roman numerals with Arabic numbers (must be whole words)
    roman_map = {
        ' i ': ' 1 ',
        ' ii ': ' 2 ',
        ' iii ': ' 3 ',
        ' iv ': ' 4 ',
        ' v ': ' 5 ',
        ' vi ': ' 6 ',
        ' vii ': ' 7 ',
        ' viii ': ' 8 ',
        ' ix ': ' 9 ',
        ' x ': ' 10 '
    }

    # Add spaces around to match word boundaries
    normalized = f" {normalized} "

    # Replace Roman numerals
    for roman, arabic in roman_map.items():
        normalized = normalized.replace(roman, arabic)

    # Remove extra spaces
    normalized = ' '.join(normalized.split())

    return normalized


# PREREQUISITE CHECKING FUNCTIONS

def get_course_prerequisites(course_code: str, db_path: str = "core/courses.db") -> Optional[Dict]:
    """
    Query the courses.db database for prerequisite information.

    Args:
        course_code: Course code to look up (e.g., "MATH 01132")
        db_path: Path to the SQLite database

    Returns:
        Dict with keys: course_code, expr, valid, not_found
        Returns None if course not found
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Normalize the course code for lookup
        normalized_code = course_code.strip().upper()

        cursor.execute("SELECT * FROM courses WHERE course_code = ?", (normalized_code,))
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
    except Exception:
        return None


def evaluate_prerequisites(prereq_expr: str, completed_courses: Set[str]) -> Tuple[bool, List[Dict]]:
    """
    Evaluate a prerequisite expression against completed courses.
    Handles AND, OR, and parentheses in prerequisite expressions.

    Args:
        prereq_expr: Prerequisite expression from database (e.g., "MATH 01131 and (CS 01100 or CS 01101)")
        completed_courses: Set of normalized course codes the student has completed

    Returns:
        Tuple of (all_met: bool, details: List[Dict])
        - all_met: True if all prerequisites are satisfied
        - details: List of dicts with prerequisite status information
    """
    if not prereq_expr or prereq_expr.strip() == "":
        return True, [{"type": "none", "message": "No prerequisites"}]

    # Pattern to match course codes
    course_pattern = r"[A-Z]{2,4}\s+\d{5}"

    # Extract all course codes from the expression
    required_courses = re.findall(course_pattern, prereq_expr)

    # Normalize completed courses for comparison
    normalized_completed = {normalize_course_code(c) for c in completed_courses}

    # Build Python-evaluable expression
    # Replace course codes with True/False based on completion
    eval_expr = prereq_expr
    course_status = {}

    for course in required_courses:
        normalized = normalize_course_code(course)
        is_completed = normalized in normalized_completed
        course_status[course] = is_completed
        # Replace with True/False for evaluation
        eval_expr = eval_expr.replace(course, str(is_completed))

    # Replace 'and' and 'or' with Python operators
    eval_expr = eval_expr.replace(" and ", " and ")
    eval_expr = eval_expr.replace(" or ", " or ")

    try:
        # Evaluate the expression
        all_met = eval(eval_expr)
    except Exception:
        # If evaluation fails, return False
        return False, [{"type": "error", "message": f"Failed to evaluate: {prereq_expr}"}]

    # Build detailed status
    details = parse_prerequisite_groups(prereq_expr, course_status)

    return all_met, details


def parse_prerequisite_groups(prereq_expr: str, course_status: Dict[str, bool]) -> List[Dict]:
    """
    Parse prerequisite expression into logical groups for display.

    Args:
        prereq_expr: Original prerequisite expression
        course_status: Dict mapping course codes to completion status

    Returns:
        List of dicts describing prerequisite groups
    """
    details = []

    # Simple case: single course
    if len(course_status) == 1:
        course = list(course_status.keys())[0]
        status = "COMPLETED" if course_status[course] else "NOT MET"
        details.append({
            "type": "single",
            "course": course,
            "status": status,
            "met": course_status[course]
        })
        return details

    # Check for OR groups (parentheses with 'or')
    or_pattern = r'\(([^)]+)\s+or\s+([^)]+)\)'
    or_matches = list(re.finditer(or_pattern, prereq_expr))

    if or_matches:
        for match in or_matches:
            group_text = match.group(0)
            # Extract courses from this group
            course_pattern = r"[A-Z]{2,4}\s+\d{5}"
            group_courses = re.findall(course_pattern, group_text)

            # Check if any course in the OR group is met
            any_met = any(course_status.get(c, False) for c in group_courses)

            group_details = {
                "type": "or_group",
                "courses": [],
                "met": any_met
            }

            for course in group_courses:
                group_details["courses"].append({
                    "course": course,
                    "status": "COMPLETED" if course_status.get(course, False) else "NOT MET",
                    "met": course_status.get(course, False)
                })

            details.append(group_details)

    # Add remaining courses (those not in OR groups) as AND requirements
    courses_in_groups = set()
    for match in or_matches:
        course_pattern = r"[A-Z]{2,4}\s+\d{5}"
        courses_in_groups.update(re.findall(course_pattern, match.group(0)))

    and_courses = [c for c in course_status.keys() if c not in courses_in_groups]

    for course in and_courses:
        status = "COMPLETED" if course_status[course] else "NOT MET"
        details.append({
            "type": "and",
            "course": course,
            "status": status,
            "met": course_status[course]
        })

    return details


def format_prerequisite_status(all_met: bool, details: List[Dict]) -> str:
    """
    Format prerequisite status into human-readable text.

    Args:
        all_met: Whether all prerequisites are met
        details: Detailed prerequisite information from evaluate_prerequisites

    Returns:
        Formatted string for display
    """
    if not details:
        return "PREREQUISITES: None"

    if details[0].get("type") == "none":
        return "PREREQUISITES: None"

    if details[0].get("type") == "error":
        return f"PREREQUISITES: {details[0]['message']}"

    output = ["PREREQUISITES:"]

    for detail in details:
        if detail["type"] == "single":
            output.append(f"{detail['course']} - {detail['status']}")
        elif detail["type"] == "and":
            output.append(f"{detail['course']} - {detail['status']}")
        elif detail["type"] == "or_group":
            output.append("(Choose one of the following):")
            for course_info in detail["courses"]:
                output.append(f"  {course_info['course']} - {course_info['status']}")
            group_status = "[OK] Requirement met" if detail["met"] else "[!] Need one of these"
            output.append(f"  {group_status}")

    output.append("")
    if all_met:
        output.append("STATUS: You have met all prerequisites for this course")
    else:
        output.append("STATUS: You have NOT met all prerequisites for this course")

    return "\n".join(output)

