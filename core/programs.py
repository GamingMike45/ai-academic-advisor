from bs4 import BeautifulSoup
import re, requests, json, unicodedata, os
from urllib.parse import urljoin


def scrape_programs(save_path):
    """
    Scrape programs from all Rowan catalog sections (including Dual, Accelerated, Combined) and save each to a JSON file.

    Args:
        save_path: Path to folder to save scraped JSON files
    
    Returns:
        None unless save_path is None, then returns a dict of all programs.
    """
    
    BASE_URL = "https://catalog.rowan.edu/"
    ROOT_URL = "content.php?catoid=13&navoid=1028"
    HEADINGS_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']

    os.makedirs(save_path, exist_ok=True)

    programs = {}
    visited_pages = set()

    def process_catalog_page(url, current_campus=None):
        # Process a catalog page and follow sub-navigation links.
        if url in visited_pages:
            return
        visited_pages.add(url)

        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to get catalog page: {url}")
            return
        soup = BeautifulSoup(response.content, 'html.parser')

        block_content = soup.find('td', class_="block_content")
        if not block_content:
            return

        # Iterate through children of block_content
        for child in block_content.children:
            if child.name == "p":
                current_campus = child.get_text(strip=True)
                programs[current_campus] = []
            elif child.name == "ul":
                assert current_campus, "No current campus found"
                for li in child.find_all('li'):
                    a_tag = li.find('a')
                    if not a_tag:
                        continue
                    href = a_tag['href']
                    program_name = a_tag.get_text(strip=True)

                    # Convert to absolute URL
                    full_url = urljoin(BASE_URL, href)

                    # Handle sub-navigation pages (recursive)
                    if "content.php" in href and "navoid=" in href:
                        process_catalog_page(full_url, current_campus=current_campus)
                        continue

                    # Only process degree pages
                    if "preview_program.php" in href or "preview_degree_planner.php" in href:
                        degree_url = re.sub("preview_program.php", "preview_degree_planner.php", href)
                        degree_url = urljoin(BASE_URL, degree_url)

                        print(f"Processing {program_name} at {degree_url}")
                        resp = requests.get(degree_url)
                        if resp.status_code != 200:
                            print(f"Failed to get {program_name} page at {degree_url}")
                            continue

                        page_soup = BeautifulSoup(resp.text, 'html.parser')

                        program_entry = {
                            "name": program_name,
                            "url": degree_url,
                            "content": {}
                        }

                        # Extract content based on headings and table rows
                        last_heading = None
                        for tr in page_soup.find_all('tr'):
                            for tag in HEADINGS_TAGS:
                                heading = tr.find(tag)
                                if heading:
                                    heading_text = heading.get_text(strip=True)
                                    program_entry["content"][heading_text] = []
                                    last_heading = heading_text
                                    break
                            if last_heading:
                                text = tr.get_text(separator=" ", strip=True).replace("\xa0", " ")
                                program_entry["content"][last_heading].append(text)

                        programs[current_campus].append(program_entry)

    # Start scraping from the main page
    process_catalog_page(BASE_URL + ROOT_URL)

    # Save results
    for campus in programs:
        for program in programs[campus]:
            filename = f"{program['name'].lower().replace(' ', '_').replace('/', ' ').replace(':', '').replace('&', 'and')}.json"
            filepath = os.path.join(save_path, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(program, f, ensure_ascii=False, indent=4)
            print(f"Saved {program['name']} to {filepath}")

    print("All catalog programs scraped successfully.")


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

def transform_course_sections_in_json(input_folder, output_folder):
    """
    Update all JSONs in input folder and save to output folder:
      - Leave already formatted {"courses": [...], "notes": [...]} untouched
      - Convert course-list sections into structured objects
      - Group courses with AND/OR logic where detected
      - Preserve everything else

    Args:
        input_folder: Path to folder with input JSON files  

        output_folder: Path to folder to save transformed JSON files

    Returns:
        None
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    for filename in os.listdir(input_folder):
        if not filename.endswith(".json"):
            continue
        
        input_filepath = os.path.join(input_folder, filename)
        output_filepath = os.path.join(output_folder, filename)
        
        with open(input_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        content = data.get("content", {})
        updated_content = {}
        
        for header, value in content.items():
            if isinstance(value, dict) and "courses" in value and "notes" in value:
                updated_content[header] = value
                continue
            
            if isinstance(value, list) and any("Credits" in v or re.search(r"[A-Z]{2,5}\s+\d{3,5}", v) for v in value):
                course_groups = []
                notes = []
                current_group = {"type": "and", "courses": []}
                or_buffer = []
                lines = [line.strip() for line in value if line.strip() and not line.strip().lower().startswith("course name")]
                i = 0
                
                while i < len(lines):
                    line = lines[i].strip()
                    
                    # Handle OR logic
                    if line.lower() == "or":
                        i += 1
                        if i >= len(lines):
                            break
                        next_line = lines[i]
                        parsed = course_transformer_into_json(next_line)
                        parsed.setdefault("credits", None)
                        
                        # If starting OR chain, move previous course into it due to implicit OR
                        if not or_buffer and current_group["courses"]:
                            or_buffer.append(current_group["courses"].pop())
                        
                        or_buffer.append(parsed)
                        
                        # If next token is not another "or", close this OR group
                        if i + 1 >= len(lines) or lines[i + 1].lower() != "or":
                            if or_buffer:
                                course_groups.append({"type": "or", "courses": or_buffer})
                                or_buffer = []
                        i += 1
                        continue
                    
                    # Handle AND logic explicitly
                    if line.lower() == "and":
                        if current_group["courses"]:
                            course_groups.append(current_group)
                        current_group = {"type": "and", "courses": []}
                        i += 1
                        continue
                    
                    # Skip or note lines
                    if re.search(r"(students|select|choose|varies|option|note|requirement|authorized)", line, re.I):
                        notes.append(line)
                        i += 1
                        continue
                    
                    # Normal course line
                    parsed = course_transformer_into_json(line)
                    parsed.setdefault("credits", None)
                    
                    if parsed["subject"] and parsed["course_number"]:
                        current_group["courses"].append(parsed)
                    else:
                        notes.append(line)
                    
                    i += 1
                
                # Finalize any open groups
                if current_group["courses"]:
                    course_groups.append(current_group)
                if or_buffer:
                    course_groups.append({"type": "or", "courses": or_buffer})
                
                updated_content[header] = {
                    "requirements": course_groups,
                    "notes": notes
                }
            else:
                updated_content[header] = value
        
        data["content"] = updated_content
        
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        print(f"Processed {filename}: structured course sections added/retained.")

if __name__ == "__main__":
    input_folder = "path/to/input/folder"
    output_folder = "path/to/output/folder"
    transform_course_sections_in_json(input_folder, output_folder)