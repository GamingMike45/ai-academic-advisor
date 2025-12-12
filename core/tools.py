# This is because llm.py was getting large and unwieldy.
"""
Academic Advisor Tools

This module contains all tool implementations for the academic advisor LLM agent.
Each tool retrieves and formats specific student data from transcripts or degree files.
"""

import os
import re
import json
import traceback
from typing import Dict, Any, Optional
from core.preqtester import PreqTester 
from core.helpers import *
from difflib import SequenceMatcher
import core.helpers as helpers

# TODO: ADD TOOLS FOR LLM HERE
class AdvisorTools:
    """Collection of tools for academic advising. All tools return formatted plain text."""
    
    def __init__(self):
        """Initialize tools with grade mappings and vault path."""
        self.GRADES = {
            "W": "withdrawn",
            "TR": "transfered"
        }

        self.courses_path = os.path.join(os.path.dirname(__file__), "vault", "courses.json")

        # Verify the path exists
        if not os.path.exists(self.courses_path):
            raise FileNotFoundError(f"Courses directory not found at: {self.courses_path}")

        self.preqtester = PreqTester(self.courses_path)
        
    
    # DATA RETRIEVAL TOOLS
    
    def get_student_info(self, transcript: Dict[str, Any]) -> str:
        """
        Get basic student information from transcript.
        
        Args:
            transcript (Dict[str, Any]): Student transcript dictionary containing:
                - name (str): Student's full name
                - major (str): Student's major(s)
                - concentration (str): Student's concentration/specialization
                - program (str): Degree program (e.g., "Bachelor of Science")
                - gpa (float): Current GPA
                - earned_credits (float): Total credits completed
                - quality_points (float): Total quality points earned
        
        Returns:
            str: Formatted text with student information, one field per line.
                 Returns "N/A" for any missing fields.
        
        Example Output:
            [STUDENT INFORMATION]
            Name: JOHNY SINS
            Major: Computer Science
            Concentration: Data Science
            Program: Bachelor of Science
            GPA: 3.255
            Completed Credits: 110.0
            Quality Points: 143.2
        """
        output_lines = [
            "[STUDENT INFORMATION]",
            f"Name: {transcript.get('name', 'N/A')}",
            f"Major: {transcript.get('major', 'N/A')}",
            f"Concentration: {transcript.get('concentration', 'N/A')}",
            f"Program: {transcript.get('program', 'N/A')}",
            f"GPA: {transcript.get('gpa', 'N/A')}",
            f"Completed Credits: {transcript.get('earned_credits', 0)}",
            f"Quality Points: {transcript.get('quality_points', 0)}"
        ]
        return "\n".join(output_lines)
    
    def get_completed_courses(self, transcript: Dict[str, Any], term: Optional[str] = None) -> str:
        """
        Get all completed courses including transfer credits.
        
        Args:
            transcript (Dict[str, Any]): Student transcript dictionary
            term (Optional[str]): Optional term filter (case-insensitive)
        
        Returns:
            str: TOON-formatted text listing all completed courses
        """
        output_lines = ["[COMPLETED COURSES]"]
        
        # Build data structure for TOON conversion
        courses_data = {}
        
        # Add transfer courses first
        if 'transfer' in transcript and transcript['transfer']:
            transfer_courses = []
            for course in transcript['transfer']:
                # Strip 'T' from transfer grades
                raw_grade = str(course['grade']).strip().strip('T')
                grade = self.GRADES.get(raw_grade, raw_grade)
                
                transfer_courses.append({
                    'code': f"{course['subject']} {course['course_number']}",
                    'title': course['title'],
                    'grade': grade,
                    'credits': course['credits']
                })
            courses_data['transfer'] = transfer_courses
        
        # Add completed courses
        if 'completed' in transcript:
            completed = transcript['completed']
            
            # Filter by term if specified
            if term:
                completed = [t for t in completed if term.lower() in t['term'].lower()]
            
            for term_data in completed:
                term_courses = []
                for course in term_data['courses']:
                    grade = self.GRADES.get(course['grade'], course['grade'])
                    term_courses.append({
                        'code': f"{course['subject']} {course['course_number']}",
                        'title': course['title'],
                        'grade': grade,
                        'credits': course['credits']
                    })
                courses_data[term_data['term']] = term_courses
        
        if not courses_data:
            return "No completed courses found"
        
        # Convert to TOON format
        toon_output = json_to_toon_robust(courses_data)
        output_lines.append(toon_output)
        
        return "\n".join(output_lines)
    
    def get_inprogress_courses(self, transcript: Dict[str, Any]) -> str:
        """
        Get courses currently in progress (enrolled but not yet completed).
        
        Args:
            transcript (Dict[str, Any]): Student transcript dictionary
        
        Returns:
            str: TOON-formatted text listing all in-progress courses
        """
        if 'inprogress' not in transcript:
            return "No courses in progress"
        
        output_lines = ["[IN-PROGRESS COURSES]"]
        
        # Build data structure for TOON conversion
        inprogress_data = {}
        
        for term_data in transcript['inprogress']:
            term_courses = []
            for course in term_data['courses']:
                term_courses.append({
                    'code': f"{course['subject']}{course['course_number']}",
                    'title': course['title'],
                    'credits': course['credits']
                })
            inprogress_data[f"{term_data['term']} (IN PROGRESS)"] = term_courses
        
        # Convert to TOON format
        toon_output = json_to_toon_robust(inprogress_data)
        output_lines.append(toon_output)
        
        return "\n".join(output_lines)
    
    def get_degree_data(self, transcript: Dict[str, Any], content_filter: str = "all") -> str:
        """
        Helper function to get degree data with optional content filtering.

        Args:
            transcript: Student transcript dictionary
            content_filter: "all", "courses", or "description"
            degree: Optional degree filename in lowercase format (e.g., "bachelor_of_science_in_computer_science")
                   If provided, uses this specific degree file instead of extracting from transcript
        """
        try:
            # If degree is explicitly provided, normalize and use it
            # IDK why at some point it decided to start passing URLs here
            # added fuzzy checker
            if degree:
                normalized_degree = helpers.normalize_degree_format(degree)
                if normalized_degree is None:
                    return f"Error: Invalid degree format '{degree}'. Please use format like 'bachelor_of_science_in_data_science', not URLs."
                degree_filenames = [f"{normalized_degree}.json"]
            else:
                # Fall back to extracting from transcript
                program = transcript.get('program', '')
                major = transcript.get('major', '')

                if not program or not major:
                    return "Error: Program or major not found in transcript"

                degree_filenames = [
                    helpers.degree2file(program.split(",")[i].strip(), m.strip())
                    for i, m in enumerate(major.split(","))
                ]
            
            if content_filter == "courses":
                output_lines = ["[DEGREE REQUIREMENTS]"]
            elif content_filter == "description":
                output_lines = ["[DEGREE DESCRIPTION]"]
            else:
                output_lines = ["[DEGREE INFORMATION]"]
            
            for degree_file in degree_filenames:
                degree_path = os.path.join(self.vault_path, degree_file)
                
                if not os.path.exists(degree_path):
                    return f"Error: Degree file not found: {degree_file}"
                
                # Use existing helper function
                degree_content = helpers.parse_degree_requirements(degree_path)
                
                # Get degree name
                with open(degree_path, 'r', encoding='utf-8') as f:
                    degree_data = json.load(f)
                degree_name = degree_data.get("name", "Unknown Degree")
                
                output_lines.append(f"\n[{degree_name.upper()}]")
                
                # Filter content based on request
                if content_filter == "description":
                    lines = degree_content.split('\n')
                    for line in lines:
                        if line.startswith('Description:'):
                            output_lines.append(line)
                            break
                    else:
                        output_lines.append("No description found")
                elif content_filter == "courses":
                    # Filter out description
                    lines = degree_content.split('\n')
                    skip_description = False
                    for line in lines:
                        if line.startswith('Description:'):
                            skip_description = True
                            continue
                        elif line.strip() == '' and skip_description:
                            skip_description = False
                            continue
                        elif not skip_description:
                            output_lines.append(line)
                else:
                    # Return everything
                    output_lines.append(degree_content)
            
            return "\n".join(output_lines)
            
        except Exception as e:
            return f"Error getting degree data: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
    
    def get_degree_courses(self, transcript: Dict[str, Any], degree: Optional[str] = None) -> str:
        """
        Get required courses for the degree program.

        Args:
            transcript: Student transcript dictionary
            degree: Optional degree filename in lowercase format (e.g., "bachelor_of_science_in_computer_science")
        """
        return self.get_degree_data(transcript, "courses", degree)

    def extract_courses_from_text(self, text: str) -> list:
        """Helper function to extract course codes from text using regex"""
        if not text:
            return []
        
        # Pattern to match course codes like "COMP 01111", "CMS 04205", etc.
        matches = re.findall(self.preqtester.course_pattern, text)
        
        courses = []
        for subject, number in matches:
            courses.append(f"{subject} {number}")
        
        return courses

    def extract_recommendation_from_llm(self, llm_out:str):
        matches = re.search(r'<recommendation>(.*?)</recommendation>', llm_out, flags=re.DOTALL)
        if not matches:
            raise Exception("No courses recommended between <recommendation> tags")
        matches = re.findall(self.preqtester.course_pattern, matches.group(1).strip())
        return {"courses": matches}

    def validate_courses(self, transcript: dict, courses: dict, needed_credits:int) -> (bool, str):
        """
        Validate that the courses are valid and that they add up to the correct number of credits
        
        Args:
            transcript (dict): The transcript dictionary
            courses (dict): The courses dictionary
            needed_credits (int): The number of credits needed

        Returns:
            tuple: (boolean, <why it failed>)

        """
        completed = get_completed_courses(transcript)

        total_credits:float = 0
        # loop through courses, validate them, and add up the credits for the recommendation
        for crse in courses:
            crse = re.search(self.preqtester.course_pattern, crse)
            if not crse:
                return False, f"incorrect course format ({crse})"

            crse = crse.group()

            if crse in completed:
                return False, f"course ({crse}) already completed"

            if crse not in set(self.preqtester.courses['CourseCode']):
                return False, f"course ({crse}) not found in catalog"

            crse = self.preqtester.find_course(crse)

            # check for preq satisfaction
            satisfied = self.preqtester(crse['CourseCode'], list(completed.keys()))

            # if not satisfied, list the courses that will satisfy the preq
            if not satisfied:
                _c = crse['CourseCode']
                _reason = f"course ({_c}) is missing prerequisistes\n"
                _reason += f"taking these courses will satisfy the prerequisistes for ({_c}): \n"

                # find courses that will satisfy the preq
                for x in self.preqtester.courses_to_satisfy(_c, list(completed.keys())):
                    x = self.preqtester.find_course(x)
                    _reason += f"\t{x['CourseCode']} - {x['CourseTitle']} ({x['Credits']} credits)\n"
                return False, _reason

            # some credits are just None in the database, they will be 0
            credits = crse['Credits'] if crse['Credits'] else 0

            if isinstance(credits, str) and 'to' in credits:
                # some credits are '1 to 3', we take latter
                credits = credits.split('to')

                assert len(credits) == 2, f"credits {credits} not in format '[X, Y]'"
                assert credits[1].strip().isnumeric(), f"credits {credits}, the latter is not numeric"

                credits = credits[1].strip()

            total_credits += float(credits)

        assert isinstance(total_credits, float), f"total credits {total_credits} is not a float"

        if total_credits > needed_credits:
            diff = needed_credits - total_credits
            return False, f"sum of all course credits too high ({total_credits} > {needed_credits}), remove {diff} credits from this recommendation"

        if total_credits < needed_credits - 3:
            diff = needed_credits - total_credits
            return False, f"sum of all course credits too low ({total_credits} < {needed_credits - 3}), add {diff} more credits to this recommendation"

        return True, ""

    def transcript2context(self, transcript: dict):
        if 'transfer' not in transcript:
            transfer_courses = ""
        else:
            transfer_courses = "Completed Courses (Transfered):\n"
            for course in transcript['transfer']:
                grade = self.GRADES.get(course['grade'], course['grade'])
                transfer_courses += f"{course['subject']} {course['course_number']} - {course['title']} ({grade.strip('T')})\n"

        if 'completed' not in transcript:
            taken_courses = ""
        else:
            taken_courses = "Completed Courses:\n"
            for term in transcript['completed']:
                taken_courses += f"\nTerm: {term['term']}\n"
                for course in term['courses']:
                    grade = self.GRADES.get(course['grade'], course['grade'])
                    taken_courses += f"\t{course['subject']} {course['course_number']} - {course['title']} ({grade})\n"

        if 'inprogress' not in transcript:
            in_progress_courses = ""
        else:
            in_progress_courses = "In Progress Courses:\n"
            for term in transcript['inprogress']:
                in_progress_courses += f"\nTerm: {term['term']}\n"
                for course in term['courses']:
                    in_progress_courses += f"\t{course['subject']} {course['course_number']} - {course['title']}\n"

        # TODO: make sure minor is also pulled correctly
        program = transcript['program']
        major = transcript['major']
        concentration = transcript['concentration']

        degree_filenames = [degree2file(program.split(",")[i].strip(), m.strip()) for i,m in enumerate(major.split(","))]

        context = ("[STUDENT INFO]\n" +
        f"Student Name: {transcript['name']}\n" +
        f"Major: {major}\n" +
        (f"Concentration: {concentration}\n" if concentration else "") +
        f"Completed Credits: {transcript['earned_credits']}\n" +
        f"GPA: {transcript['gpa']}\n" +
        "\n\n" +
        "[STUDENT COURSES]\n" +
        f"\n{transfer_courses}\n" +
        f"\n{taken_courses}\n" +
        # f"\n{in_progress_courses}\n" +
        "\n\n")

        for d in degree_filenames:
            _degree = open(os.path.join(os.path.dirname(__file__), "vault", "degrees", d), "r").read()
            _degree = json.loads(_degree)
            degree_req = parse_degree_requirements_from_transcript(_degree, transcript)

            context += f"[DEGREE REQUIREMENTS FOR {d.upper()}]\n"
            for head, v in degree_req.items():
                head = head.replace("s.h.", "credits needed") 
                if not v['completed']:
                    context += f"{head} ({v['completed_credits']} credits taken)\n"
                    for crse_code, crse_info in v['not_completed'].items():
                        context += f"- {crse_code} - {crse_info['title']} ({crse_info['credits']})\n"
                else:
                    context += f"{head}: \ncompleted\n"

                context += "\n"
        
        return context
    def get_degree_description(self, transcript: Dict[str, Any], degree: Optional[str] = None) -> str:
        """
        Get the degree program description only.

        Args:
            transcript: Student transcript dictionary
            degree: Optional degree filename in lowercase format (e.g., "bachelor_of_science_in_computer_science")
        """
        return self.get_degree_data(transcript, "description", degree)


    def get_course_info(self, transcript: Dict[str, Any], course: str) -> str:
        """
        Get detailed information about a specific course including prerequisites check.

        Args:
            transcript: Student transcript dictionary
            course: Course code OR course title to look up (e.g., "MATH 01132", "Calculus III", "Calc 3")

        Returns:
            Formatted string with course details and prerequisite status
        """
        try:
            # Load courses database
            courses_path = "core/vault/courses.json"
            if not os.path.exists(courses_path):
                return f"Error: Courses database not found at {courses_path}"

            with open(courses_path, 'r', encoding='utf-8') as f:
                courses_db = json.load(f)

            # First, try to find by course code (exact match)
            course_obj = None
            normalized_input = helpers.normalize_course_code(course)

            for c in courses_db:
                course_code_in_db = c.get('CourseCode', '')
                normalized_db = helpers.normalize_course_code(course_code_in_db)
                if normalized_db == normalized_input:
                    course_obj = c
                    break

            # If not found by code, try to find by title (fuzzy search with Roman numeral support)
            if not course_obj:
                # Infer subject from common keywords
                inferred_subject = None
                search_lower = course.lower()
                # trying to infer subject from keywords to narrow down search and improve accuracy
                subject_keywords = {
                    'MATH': ['calc', 'calculus', 'algebra', 'geometry', 'trigonometry', 'statistics', 'math'],
                    'CS': ['programming', 'computer', 'software', 'algorithm', 'data structures', 'coding'],
                    'PHYS': ['physics'],
                    'CHEM': ['chemistry', 'chem'],
                    'BIO': ['biology', 'bio'],
                    'ENG': ['english', 'literature', 'writing'],
                    'HIST': ['history'],
                    'PSYC': ['psychology', 'psych']
                }

                for subject, keywords in subject_keywords.items():
                    if any(keyword in search_lower for keyword in keywords):
                        inferred_subject = subject
                        break

                # Normalize the search term
                normalized_search = helpers.normalize_course_title_for_search(course)
                search_words = normalized_search.split()

                matches = []

                for c in courses_db:
                    # If we inferred a subject, filter by it
                    if inferred_subject:
                        course_code = c.get('CourseCode', '')
                        if not course_code.startswith(inferred_subject):
                            continue

                    course_title = c.get('CourseTitle', '')
                    normalized_title = helpers.normalize_course_title_for_search(course_title)

                    # Strategy 1: Check if all words in search appear in title
                    all_words_match = all(word in normalized_title for word in search_words)

                    # Strategy 2: Check if search is substring of title
                    substring_match = normalized_search in normalized_title

                    if all_words_match or substring_match:
                        # Calculate a match score (prefer exact matches)
                        score = 0
                        if normalized_search == normalized_title:
                            score = 100  # Exact match
                        elif substring_match:
                            score = 50  # Substring match
                        elif all_words_match:
                            score = 25  # All words present

                        matches.append((c, score, 'exact'))

                # Sort by score (highest first)
                matches.sort(key=lambda x: x[1], reverse=True)

                # Take the best match if we have any
                if matches:
                    course_obj = matches[0][0]

            # Strategy 3: If still not found, try spelling-tolerant fuzzy matching
            spelling_corrected = False
            if not course_obj:
                # Ensure inferred_subject is defined (may not be if we found by code)
                if 'inferred_subject' not in locals():
                    inferred_subject = None
                    search_lower = course.lower()
                    subject_keywords = {
                        'MATH': ['calc', 'calculus', 'algebra', 'geometry', 'trigonometry', 'statistics', 'math'],
                        'CS': ['programming', 'computer', 'software', 'algorithm', 'data structures', 'coding'],
                        'PHYS': ['physics'],
                        'CHEM': ['chemistry', 'chem'],
                        'BIO': ['biology', 'bio'],
                        'ENG': ['english', 'literature', 'writing'],
                        'HIST': ['history'],
                        'PSYC': ['psychology', 'psych']
                    }
                    for subject, keywords in subject_keywords.items():
                        if any(keyword in search_lower for keyword in keywords):
                            inferred_subject = subject
                            break

                normalized_search = helpers.normalize_course_title_for_search(course)
                fuzzy_matches = []

                # Higher threshold for short queries to prevent false matches like "calc 4" → "clinical practice 4"
                min_threshold = 0.8 if len(normalized_search) <= 10 else 0.7

                for c in courses_db:
                    # Apply subject filter if we inferred one
                    if inferred_subject:
                        course_code_check = c.get('CourseCode', '')
                        if not course_code_check.startswith(inferred_subject):
                            continue

                    course_title = c.get('CourseTitle', '')
                    normalized_title = helpers.normalize_course_title_for_search(course_title)

                    # Use SequenceMatcher to calculate similarity ratio
                    similarity = SequenceMatcher(None, normalized_search, normalized_title).ratio()

                    # Also check word-level similarity for partial matches
                    search_words = normalized_search.split()
                    title_words = normalized_title.split()

                    # Calculate how many search words have close matches in title
                    word_match_score = 0
                    for search_word in search_words:
                        best_word_similarity = max(
                            (SequenceMatcher(None, search_word, title_word).ratio()
                             for title_word in title_words),
                            default=0
                        )
                        word_match_score += best_word_similarity

                    # Normalize word match score
                    if search_words:
                        word_match_score = word_match_score / len(search_words)

                    # Take the better of full-string or word-level matching
                    final_similarity = max(similarity, word_match_score)

                    # Only consider courses above the threshold
                    if final_similarity >= min_threshold:
                        fuzzy_matches.append((c, final_similarity))

                # Sort by similarity (highest first)
                fuzzy_matches.sort(key=lambda x: x[1], reverse=True)

                # Take the best fuzzy match if we have any
                if fuzzy_matches:
                    course_obj = fuzzy_matches[0][0]
                    spelling_corrected = True

            if not course_obj:
                return f"Course not found: {course}\nPlease try using either the course code (e.g., 'MATH 01133') or course title (e.g., 'Calculus III')"

            # Build output
            output_lines = ["[ COURSE INFORMATION ]"]
            output_lines.append("")

            # If we used spelling correction, note what we matched
            if spelling_corrected:
                output_lines.append(f"(Showing results for '{course_obj.get('CourseTitle', 'N/A')}')")
                output_lines.append("")

            output_lines.append(f"Course: {course_obj.get('CourseCode', 'N/A')}")
            output_lines.append(f"Title: {course_obj.get('CourseTitle', 'N/A')}")
            output_lines.append(f"Credits: {course_obj.get('Credits', 'N/A')}")
            output_lines.append("")

            # Add description if available
            description = course_obj.get('Description', '')
            if description:
                output_lines.append(f"Description: {description}")
                output_lines.append("")

            # Check prerequisites using courses.db
            course_code = course_obj.get('CourseCode', '')
            prereq_data = helpers.get_course_prerequisites(course_code)

            if prereq_data and prereq_data.get('expr'):
                # Build set of completed courses from transcript
                completed = set()
                if 'transfer' in transcript:
                    for t_course in transcript['transfer']:
                        code = f"{t_course['subject']} {t_course['course_number']}"
                        completed.add(code)

                if 'completed' in transcript:
                    for term_data in transcript['completed']:
                        for t_course in term_data['courses']:
                            code = f"{t_course['subject']} {t_course['course_number']}"
                            # Only count if passing grade
                            if helpers.is_passing_grade(t_course.get('grade', 'F')):
                                completed.add(code)

                # Evaluate prerequisites with AND/OR logic
                all_met, prereq_details = helpers.evaluate_prerequisites(
                    prereq_data['expr'],
                    completed
                )

                # Format and display prerequisite status
                prereq_status = helpers.format_prerequisite_status(all_met, prereq_details)
                output_lines.append(prereq_status)
            else:
                output_lines.append("PREREQUISITES: None")

            return "\n".join(output_lines)

        except Exception as e:
            return f"Error getting course info: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

    def search_courses(self, transcript: Dict[str, Any], subject: Optional[str] = None,
                      eligible_only: bool = False, credits: Optional[str] = None,
                      keyword: Optional[str] = None, max_results: int = 20) -> str:
        """
        Search for courses by various criteria.

        Args:
            transcript: Student transcript dictionary
            subject: Filter by subject code (e.g., "CS", "MATH")
            eligible_only: Only show courses student has prerequisites for (default: False)
            credits: Filter by credit count (e.g., "3")
            keyword: Search keyword in course titles and descriptions
            max_results: Maximum number of results to return (default: 20)

        Returns:
            Formatted string with list of matching courses
        """
        try:
            # Load courses database
            courses_path = "core/vault/courses.json"
            if not os.path.exists(courses_path):
                return f"Error: Courses database not found at {courses_path}"

            with open(courses_path, 'r', encoding='utf-8') as f:
                courses_db = json.load(f)

            # Build set of completed courses if checking eligibility
            completed = set()
            if eligible_only:
                if 'transfer' in transcript:
                    for course in transcript['transfer']:
                        code = f"{course['subject']} {course['course_number']}"
                        completed.add(code)

                if 'completed' in transcript:
                    for term_data in transcript['completed']:
                        for course in term_data['courses']:
                            code = f"{course['subject']} {course['course_number']}"
                            if helpers.is_passing_grade(course.get('grade', 'F')):
                                completed.add(code)

            # Filter courses
            matches = []
            for course in courses_db:
                course_code = course.get('CourseCode', '')
                course_title = course.get('CourseTitle', '')
                course_credits = course.get('Credits', '')
                course_desc = course.get('Description', '')

                # Get prerequisite expression from courses.db
                prereq_data = helpers.get_course_prerequisites(course_code)
                prereq_expr = prereq_data.get('expr', '') if prereq_data else ''

                # Apply subject filter
                if subject:
                    # Extract subject from course code (e.g., "MATH 01230" -> "MATH")
                    course_subject = course_code.split()[0] if ' ' in course_code else course_code[:2]
                    if course_subject.upper() != subject.upper():
                        continue

                # Apply credits filter
                if credits:
                    if course_credits != credits:
                        continue

                # Apply keyword filter
                if keyword:
                    keyword_lower = keyword.lower()
                    if (keyword_lower not in course_title.lower() and
                        keyword_lower not in course_desc.lower()):
                        continue

                # Apply eligibility filter using courses.db
                eligible = True
                if eligible_only:
                    if prereq_expr:
                        # Evaluate prerequisites with AND/OR logic
                        all_met, _ = helpers.evaluate_prerequisites(
                            prereq_expr,
                            completed
                        )
                        eligible = all_met

                        if not eligible:
                            continue

                # Add to matches
                matches.append({
                    'code': course_code,
                    'title': course_title,
                    'credits': course_credits,
                    'prereqs': prereq_expr,
                    'eligible': eligible
                })

                # Stop if we hit max results
                if len(matches) >= max_results:
                    break

            # Build TOON-formatted output
            search_data = {}

            # Build filter description
            filters = []
            if subject:
                filters.append(f"subject:{subject}")
            if credits:
                filters.append(f"credits:{credits}")
            if keyword:
                filters.append(f"keyword:{keyword}")
            if eligible_only:
                filters.append("eligible_only:True")

            search_data['filters'] = ", ".join(filters) if filters else "none"
            search_data['found'] = len(matches)

            if not matches:
                output = "[ COURSE SEARCH ]\n"
                output += helpers.json_to_toon_robust(search_data)
                output += "\nNo courses found matching criteria"
                return output

            # Build course list
            courses_list = []
            for match in matches:
                course_data = {
                    'code': match['code'],
                    'title': match['title'],
                    'credits': match['credits']
                }

                if match['prereqs'] and match['prereqs'].strip():
                    course_data['prereqs'] = match['prereqs']

                if eligible_only:
                    course_data['eligible'] = match['eligible']

                courses_list.append(course_data)

            search_data['courses'] = courses_list

            if len(matches) >= max_results:
                search_data['note'] = f"Showing first {max_results} results"

            # Convert to TOON format
            output = "[ COURSE SEARCH ]\n"
            output += helpers.json_to_toon_robust(search_data)
            return output

        except Exception as e:
            return f"Error searching courses: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
