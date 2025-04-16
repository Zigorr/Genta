from agency_swarm import Agent

class MonitorCEO(Agent):
    def __init__(self):
        super().__init__(
            name="MonitorCEO",
            description="Manages the website monitoring process. Receives monitoring tasks (URL, selector, description) and delegates them to the WebsiteMonitor agent.",
            # Instructions for CEO are often implicitly handled by Agency structure
            # Instructions can be enhanced here or in a file if needed.
            instructions="Your role is to receive website monitoring tasks defined by a URL and a CSS selector. You must delegate the actual monitoring work to the WebsiteMonitor agent. Ensure you relay the URL and CSS selector accurately to the WebsiteMonitor agent.",
            tools=[], # CEO typically delegates, doesn't use tools directly
            # llm= # Define specific LLM if needed, otherwise inherits from Agency
        ) 