import re
import pandas as pd
import itertools
from tqdm import tqdm

# TODO: implement caching or initial parsing of all courses
# TODO: fix expression issues with "or or", mismatching parentheses, etc. 

class PreqTester():
    """
    Tests if a course can be taken given the courses taken
    
    Attributes
    ----------
    courses : pandas.DataFrame
        DataFrame containing course information
    prereqs : dict
        dictionary of all the parsed preq for all courses,
        contains "missing" key for preq courses not found in the catalog.
    """
    def __init__(self, courses_path):
        self.course_pattern = r"[A-Z]{2,4}\s*\d{4,5}" # catches CS2345 or CS 02345
        self.courses = pd.read_json(courses_path)
        self.prereqs = {}

        assert len(self.courses['CourseCode'].values) == len(self.courses), "Duplicate course codes found"

        for i in tqdm(range(len(self.courses))):
            crse = self.courses.iloc[i]
            self.prereqs[crse['CourseCode']] = self._parse_preq(crse)

    def __call__(self, course: str, taken: list[str]):
        """
        Tests if the course can be taken given the courses taken

        Args:
            course (str): The course code to test
            taken (list[str]): list of course codes

        Returns:
            bool: True if the course can be taken, False otherwise
        """

        assert course in self.prereqs, "No course found in cache"
        parsed = self.prereqs[course]
        if parsed is None:
            return True

        #TODO: write a function that finds the least amount if true courses needed to satisfy the expr,
        # and return the list of courses that need to be taken
        return eval(parsed['py_expr'], {'taken': taken})

    def courses_to_satisfy(self, course: str, taken: list[str]):
        assert course in self.prereqs, "No course found in cache"
        parsed = self.prereqs[course]
        if parsed is None:
            return []

        # extract all courses in boolean expression
        courses = re.findall(self.course_pattern, parsed['expr'])
        
        # find taken courses and not taken courses in boolean expression
        taken_in_expr = set(taken) & set(courses)
        not_taken_in_expr = set(courses) - taken_in_expr

        # find the least amount of courses needed to satisfy the expression
        for x in range(1, len(not_taken_in_expr)+1):
            for comb in itertools.combinations(not_taken_in_expr, x):
                if eval(parsed['py_expr'], {'taken': list(taken_in_expr | set(comb))}):
                    return list(comb)

        return []
  
    def find_course(self, course:str):
        if course not in set(self.courses['CourseCode']):
            raise ValueError(f"Course {course} not found in courses list")
        return self.courses[self.courses['CourseCode'] == course].iloc[0]

    def _extract_desc(self, desc: str) -> dict:
        """
        Extracts the sections from the course description
        {
            'Prerequisite Courses': 'CS 04113 with a minimum grade of C- or Math 0316 with a minimun grade of C- ...',
            'Course Attributes': 'CAT, UGRD',
            'Academic Department': 'Computer Science'
        }
        """
        heading = r"[A-Za-z]+(?: [A-Za-z]+)"
        stop = r"(?=(?:" + heading + r":)|$)"
        key = r"(?P<key>" + heading + r"):"
        pattern = key + r'\s*(?P<value>.*?)' + stop

        return {m.group("key").strip(): m.group("value").strip() for m in re.finditer(pattern, desc)}

    def _parse_preq(self, course: pd.Series):
        """
        Parses the prerequisites for a course
        """
        if not course['Prerequisites']:
            return None

        # finds preqs in Prerequisites
        preqs = re.findall(self.course_pattern, course['Prerequisites'])

        if len(preqs) < 1:
            return None

        # if there is only one Prequisite, return it
        if len(preqs) == 1:  
            out = preqs[0].strip()
            try:
                parsed = self._parse_expr(course['CourseCode'], out)
                out = eval(parsed['py_expr'], {'taken': []}) # test the expression
                return {
                    'expr': parsed['expr'],
                    'py_expr': parsed['py_expr'],
                    'valid': True,
                    'not_found': None
                }
            except Exception as e:
                # print(f"Error parsing prerequisites for {course['CourseCode']}")
                # print(f"preqs: {course['Prerequisites']}")
                # print(f"out: {out}")
                return {
                    'expr': out,
                    'valid': False,
                    'not_found': None
                }

        sections = self._extract_desc(course['Description'])
        assert "Prerequisite Courses" in sections, f'could not find "Prerequisite Courses" in the description:\n {sections}'

        # finds preqs in description
        preqs = re.findall(self.course_pattern, sections['Prerequisite Courses'])

        # check if preq course exists in course catalog
        missing = list(set(preqs) - set(self.courses['CourseCode']))

        # pull "and, (, ), or" all logic operators
        preq_regex = self.course_pattern + "|" + r"\b(?:and|or)\b|\(|\)"
        preq_raw = sections['Prerequisite Courses']
        preq_raw = preq_raw.replace("AND", "and")
        preq_raw = preq_raw.replace("OR", "or")

        out = re.findall(preq_regex, preq_raw)
        out = " ".join(out).replace("( )", "") # replace empty parentheses

        # capture everything after the first seen course code
        out = re.search(r"\(?\s{,1}" + self.course_pattern + r"(.*)", out).group(0)

        try:
            parsed = self._parse_expr(course['CourseCode'], out)
            out = eval(parsed['py_expr'], {'taken': []}) # test the expression
            return {
                "expr": parsed['expr'],
                'py_expr': parsed['py_expr'],
                "valid": True,
                "not_found": missing if len(missing) > 0 else None,
            }
        except Exception as e:
            # print(f"Error parsing prerequisites for {course['CourseCode']}")
            # print(f"preqs: {course['Prerequisites']}")
            # print(f"input: {preq_raw}")
            # print(f"output: {out}\n")
            return {
                "expr": out,
                "valid": False,
                "not_found": missing if len(missing) > 0 else None,
            }

    def _parse_expr(self, course: str, expr:str):
        # converts the preq boolean expression into valid python code 
        py_expr = re.sub(f"({self.course_pattern})", r"('\1' in taken)", expr).strip()
        return {"expr": expr, "py_expr": py_expr}

    def _find_all_combs(self, course):
        assert course in self.cache, f"No cache found for course {course['CourseCode']}"
        
        course = self.courses[self.courses['CourseCode'] == course].iloc[0]

        # preqs = ""
        if not course['Prerequisites']:
            return []

        preqs = set(re.findall(self.course_pattern, course['Prerequisites']))
        
        all_combs = []
        for i in range(1, len(preqs)+1):
            all_combs.extend(itertools.combinations(preqs, i))      

        # extract only vaild combinations
        true_combs = [all_comb for all_comb in all_combs if eval(self.cache[course['CourseCode']]['py_expr'], {"taken": all_comb})]

        return true_combs
        
        