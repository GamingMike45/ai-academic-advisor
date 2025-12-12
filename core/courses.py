from tqdm import tqdm
import requests
from bs4 import BeautifulSoup
import time

# Rowan University Course Catalog URL with pagination
# Change the page number in the URL to navigate through pages for any College
BASE_URL = "https://rowan.catalog.acalog.com/content.php?catoid=13&navoid=1029&filter[cpage]={page}&expand=1"

# Function to scrape course data
# max_pages limits how many pages to scrape 
# Rowan has ~4400 courses, about 45 pages of 50 courses each
def scrape_courses(max_pages=45, sleep=0.25):
    all_courses = []

    for page in tqdm(range(1, max_pages + 1)):
        url = BASE_URL.format(page=page)
        print(f"Scraping page {page}: {url}")
        response = requests.get(url)

        # Check if the page exists
        if response.status_code != 200:
            print(f"Page {page} not found (status {response.status_code}). Stopping.")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # All courses live inside <ul><li>
        course_blocks = soup.select("ul > li")

        if not course_blocks:
            print("No more courses found.")
            break

        for block in course_blocks:
            # --- Header (course code + title) ---
            header = block.find("h3")
            if not header:
                continue
            header_text = header.get_text(" ", strip=True)
            # Split at the first dash to separate course code and title Rowan University uses a dash
            if '-' in header_text:
                parts = header_text.split('-', 1)
                course_code = parts[0].strip()
                course_title = parts[1].strip()
            else:
                course_code = header_text.strip()
                course_title = ""

            # --- Credits ---
            credits = None
            credit_tag = block.find(string=lambda t: t and "Credits:" in t)
            if credit_tag:
                credits = credit_tag.replace("Credits:", "").strip()

            # --- Prerequisites ---
            prereq = None
            prereq_tag = block.find(string=lambda t: t and "Prerequisite Courses" in t)
            if prereq_tag:
                links = block.find_all("a")
                prereq_list = [a.get_text(strip=True) for a in links]
                prereq = ", ".join(prereq_list) if prereq_list else prereq_tag.strip()

            # --- Description ---
            # Get all raw text inside the block
            all_text = " ".join(d.strip() for d in block.stripped_strings)

            # Description is the leftover trimmed text
            description = all_text.strip()
            
            all_courses.append({
                "CourseCode": course_code,
                "CourseTitle": course_title,
                "Credits": credits,
                "Description": description,
                "Prerequisites": prereq,
            })

        time.sleep(sleep) # Be polite and avoid hammering the server

    return all_courses

    
