import requests
from agency_swarm.tools import BaseTool

# Import Field from Pydantic
try:
    from pydantic.v1 import Field
except ImportError:
    from pydantic import Field

class FetchContentTool(BaseTool):
    """Fetches HTML content from a URL using the requests library."""
    url: str = Field(..., description="The URL of the website to fetch.")

    def run(self):
        self._shared_state.set("current_url", self.url) # Store URL for other tools
        print(f"Tool: Fetching {self.url}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(self.url, headers=headers, timeout=20)
            response.raise_for_status()
            self._shared_state.set("fetched_html", response.text)
            return f"Successfully fetched content from {self.url}."
        except requests.exceptions.Timeout:
             error_msg = f"Error: Request timed out for URL: {self.url}"
             self._shared_state.set("error", error_msg)
             return error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"Error fetching URL {self.url}: {e}"
            self._shared_state.set("error", error_msg)
            return error_msg
        # TODO: Add optional Selenium/Playwright logic here if requests fail or JS is needed 