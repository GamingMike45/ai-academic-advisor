from core.embedding import ChromaDB
import core.programs
import core.helpers as helpers

#ChromaDB().embed_degrees("degrees")
#ChromaDB().embed_courses("courses/rowan_courses.json")


json_file = "core/vault/degrees/bachelor_of_science_in_computer_science.json"
print(helpers.parse_degree_requirements(json_file))
    

DATA_PATH_DEGREES = "core/vault/degrees"
DATA_PATH_COURSES = "core/vault/courses/rowan_courses.csv"
