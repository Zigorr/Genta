import os
import hashlib
from agency_swarm.tools import BaseTool

# Import Field from Pydantic
try:
    from pydantic.v1 import Field
except ImportError:
    from pydantic import Field

# --- Configuration & Globals ---
DATA_DIR = 'data'
MAX_CONTENT_SNIPPET = 200 # Max chars for notification snippet

# --- Helper Function ---
def get_file_path(url):
    """Generates a consistent file path for storing URL content."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(DATA_DIR, f"{url_hash}.txt")

class CompareAndPersistTool(BaseTool):
    """Compares extracted content with the stored version, updates storage, and reports changes."""
    # No input fields needed, uses shared state

    def run(self):
        print("Tool: Comparing and Persisting content...")
        url = self._shared_state.get("current_url")
        new_content = self._shared_state.get("extracted_content")
        fetch_extract_error = self._shared_state.get("error")

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
                self._shared_state.set("change_detected", True)
                self._shared_state.set("previous_content_snippet", previous_content[:MAX_CONTENT_SNIPPET])
                self._shared_state.set("new_content_snippet", new_content[:MAX_CONTENT_SNIPPET])
                return f"Change detected for {url}. Content updated."
            except Exception as e:
                return f"Error writing new content file {file_path}: {e}"
        else:
            print(f"No change detected for {url}.")
            self._shared_state.set("change_detected", False)
            return f"No change detected for {url}." 