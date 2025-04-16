from bs4 import BeautifulSoup
from agency_swarm.tools import BaseTool

# Import Field from Pydantic
try:
    from pydantic.v1 import Field
except ImportError:
    from pydantic import Field

class ExtractContentTool(BaseTool):
    """Extracts text from HTML using a CSS selector with BeautifulSoup."""
    selector: str = Field(..., description="The CSS selector to target the desired content.")

    def run(self):
        print(f"Tool: Extracting content with selector: {self.selector}")
        html_content = self._shared_state.get("fetched_html")
        if not html_content:
            error_msg = "Error: No fetched HTML content found in shared state."
            self._shared_state.set("error", error_msg)
            return error_msg
        if self._shared_state.get("error"): # Check if fetch failed
             return f"Skipping extraction due to fetch error: {self._shared_state.get('error')}"

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            elements = soup.select(self.selector)
            if not elements:
                error_msg = f"Error: No elements found matching selector '{self.selector}'."
                self._shared_state.set("error", error_msg)
                return error_msg

            extracted_text = ' '.join(elem.get_text(separator=' ', strip=True) for elem in elements)
            if not extracted_text:
                 extracted_text = "" # Represent no text found vs. an error

            self._shared_state.set("extracted_content", extracted_text)
            return f"Successfully extracted content using selector: {self.selector}"
        except Exception as e:
            error_msg = f"Error parsing HTML or extracting content with selector '{self.selector}': {e}"
            self._shared_state.set("error", error_msg)
            return error_msg 