from agency_swarm.tools import BaseTool

# Import Field from Pydantic
try:
    from pydantic.v1 import Field
except ImportError:
    from pydantic import Field

class NotificationTool(BaseTool):
    """Sends a notification if a change was detected."""
    # No input fields needed, uses shared state

    def run(self):
        print("Tool: Checking for notification...")
        if self._shared_state.get("change_detected"):
            url = self._shared_state.get("current_url", "Unknown URL")
            new_snippet = self._shared_state.get("new_content_snippet", "N/A")

            message = f"Content change detected for: {url}\n"
            message += f"New Snippet: {new_snippet}...\n"
            message += "(Full content updated in storage.)"

            print("\n--- ALERT --- ALERT --- ALERT ---")
            print(message)
            print("--- END ALERT ---\n")
            return message
        else:
            return "No change detected, no notification sent." 