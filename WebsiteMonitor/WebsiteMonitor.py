from agency_swarm import Agent
# from .tools import FetchContentTool, ExtractContentTool, CompareAndPersistTool, NotificationTool
from .tools.fetch_content_tool import FetchContentTool
from .tools.extract_content_tool import ExtractContentTool
from .tools.compare_and_persist_tool import CompareAndPersistTool
from .tools.notification_tool import NotificationTool

class WebsiteMonitor(Agent):
    def __init__(self):
        super().__init__(
            name="WebsiteMonitor",
            description="Responsible for fetching, extracting, comparing, and potentially notifying about changes for a single specified website URL and CSS selector.",
            instructions="./instructions.md", # Load from instructions.md
            tools=[FetchContentTool, ExtractContentTool, CompareAndPersistTool, NotificationTool],
            # llm= # Define specific LLM if needed
        ) 