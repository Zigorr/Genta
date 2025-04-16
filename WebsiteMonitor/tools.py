import os
import requests
import hashlib
from bs4 import BeautifulSoup
from agency_swarm.tools import BaseTool

# Import Field from Pydantic
try:
    from pydantic.v1 import Field
except ImportError:
    from pydantic import Field

# --- Configuration & Globals (Consider moving to a central config if needed) ---
DATA_DIR = 'data'
MAX_CONTENT_SNIPPET = 200 # Max chars for notification snippet

# --- Helper Function --- Needed by tools here
def get_file_path(url):
    """Generates a consistent file path for storing URL content."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(DATA_DIR, f"{url_hash}.txt")

# --- Tool Definitions ---

class FetchContentTool(BaseTool):
    """Fetches HTML content from a URL using the requests library."""
    url: str = Field(..., description="The URL of the website to fetch.")

    def run(self):
        self.shared_state.set("current_url", self.url) # Store URL for other tools
        print(f"Tool: Fetching {self.url}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(self.url, headers=headers, timeout=20)
            response.raise_for_status()
            self.shared_state.set("fetched_html", response.text)
            return f"Successfully fetched content from {self.url}."
        except requests.exceptions.Timeout:
             error_msg = f"Error: Request timed out for URL: {self.url}"
             self.shared_state.set("error", error_msg)
             return error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"Error fetching URL {self.url}: {e}"
            self.shared_state.set("error", error_msg)
            return error_msg
        # TODO: Add optional Selenium/Playwright logic here if requests fail or JS is needed

class ExtractContentTool(BaseTool):
    """Extracts text from HTML using a CSS selector with BeautifulSoup."""
    selector: str = Field(..., description="The CSS selector to target the desired content.")

    def run(self):
        print(f"Tool: Extracting content with selector: {self.selector}")
        html_content = self.shared_state.get("fetched_html")
        if not html_content:
            error_msg = "Error: No fetched HTML content found in shared state."
            self.shared_state.set("error", error_msg)
            return error_msg
        if self.shared_state.get("error"): # Check if fetch failed
             return f"Skipping extraction due to fetch error: {self.shared_state.get('error')}"

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            elements = soup.select(self.selector)
            if not elements:
                error_msg = f"Error: No elements found matching selector '{self.selector}'."
                self.shared_state.set("error", error_msg)
                return error_msg

            extracted_text = ' '.join(elem.get_text(separator=' ', strip=True) for elem in elements)
            if not extracted_text:
                 extracted_text = "" # Represent no text found vs. an error

            self.shared_state.set("extracted_content", extracted_text)
            return f"Successfully extracted content using selector: {self.selector}"
        except Exception as e:
            error_msg = f"Error parsing HTML or extracting content with selector '{self.selector}': {e}"
            self.shared_state.set("error", error_msg)
            return error_msg

class CompareAndPersistTool(BaseTool):
    """Compares extracted content with the stored version, updates storage, and reports changes."""
    # No input fields needed, uses shared state

    def run(self):
        print("Tool: Comparing and Persisting content...")
        url = self.shared_state.get("current_url")
        new_content = self.shared_state.get("extracted_content")
        fetch_extract_error = self.shared_state.get("error")

        if fetch_extract_error:
            return f"Skipping compare/persist due to error: {fetch_extract_error}"
        if url is None:
            return "Error: URL not found in shared state for comparison."
        if new_content is None:
             new_content = ""

        file_path = get_file_path(url)
        previous_content = ""
        change_detected = False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                previous_content = f.read()
        except FileNotFoundError:
            print(f"No previous data found for {url}. First check.")
            change_detected = True
        except Exception as e:
            return f"Error reading previous content file {file_path}: {e}"

        if not change_detected and previous_content != new_content:
            print(f"Change detected for {url}.")
            change_detected = True

        if change_detected:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated stored content for {url}.")
                self.shared_state.set("change_detected", True)
                self.shared_state.set("previous_content_snippet", previous_content[:MAX_CONTENT_SNIPPET])
                self.shared_state.set("new_content_snippet", new_content[:MAX_CONTENT_SNIPPET])
                return f"Change detected for {url}. Content updated."
            except Exception as e:
                return f"Error writing new content file {file_path}: {e}"
        else:
            print(f"No change detected for {url}.")
            self.shared_state.set("change_detected", False)
            return f"No change detected for {url}."

class NotificationTool(BaseTool):
    """Sends a notification if a change was detected."""
    # No input fields needed, uses shared state

    def run(self):
        print("Tool: Checking for notification...")
        if self.shared_state.get("change_detected"):
            url = self.shared_state.get("current_url", "Unknown URL")
            new_snippet = self.shared_state.get("new_content_snippet", "N/A")

            message = f"Content change detected for: {url}\n"
            message += f"New Snippet: {new_snippet}...\n"
            message += "(Full content updated in storage.)"

            print("\n--- ALERT --- ALERT --- ALERT ---")
            print(message)
            print("--- END ALERT ---\n")
            return "Notification sent (printed to console)."
        else:
            return "No change detected, no notification sent." 