# Website Content Monitor Agency (using agency-swarm)

This project uses the `agency-swarm` library and a large language model (LLM) like OpenAI's GPT to monitor specified websites for changes in specific content areas.

## Features

*   Reads target websites and CSS selectors from `config.json`.
*   Periodically fetches website content using `requests`.
*   Extracts text from specified sections using `BeautifulSoup`.
*   Compares extracted content with the last known version stored locally.
*   Stores the latest version of the content in the `data/` directory.
*   Sends a notification (prints to console) if a change is detected.
*   Uses the `agency-swarm` framework with a `MonitorCEO` agent orchestrating a `WebsiteMonitor` worker agent.
*   Follows a structure similar to other `agency-swarm` projects, with agents and tools organized in folders.

## Project Structure

```
/
├── MonitorCEO/
│   ├── MonitorCEO.py       # Defines the CEO agent
│   └── __init__.py
├── WebsiteMonitor/
│   ├── WebsiteMonitor.py   # Defines the worker agent
│   ├── instructions.md     # Instructions for the worker agent
│   ├── tools.py            # Defines tools used by the worker
│   └── __init__.py
├── data/                     # Stores last known content (auto-created)
├── SMM-2.1-Fork-main/      # Reference project (you added this)
├── .env                      # Stores API keys (you need to create/update this)
├── agency.py                 # Main script to run the agency
├── config.json               # Configuration for websites to monitor
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Setup

1.  **Environment Variables (`.env` file):**
    *   Create or ensure you have a `.env` file in the root directory.
    *   Add your OpenAI API key, as `agency-swarm` defaults to using OpenAI:
        ```dotenv
        OPENAI_API_KEY="YOUR_OPENAI_API_KEY_HERE"
        # Add other keys if needed
        ```
    *   **Important:** Add `.env` to your `.gitignore` file.

2.  **Dependencies (`requirements.txt`):**
    *   Install the required Python libraries:
        ```bash
        pip install -r requirements.txt
        ```

3.  **Configuration (`config.json`):**
    *   Edit the `config.json` file to define the websites you want to monitor.
    *   Each entry should have `url`, `selector`, and `description`.
    *   Example:
        ```json
        [
          {
            "url": "https://example.com",
            "selector": "body > div > p:nth-of-type(1)",
            "description": "First paragraph on example.com"
          }
        ]
        ```

## How to Run

1.  **Complete Setup:** Ensure steps 1-3 above are done.
2.  **Run from Terminal:** Execute the main agency script:
    ```bash
    python agency.py
    ```
3.  **Monitoring Loop:**
    *   The script will start and initialize the agency.
    *   It will then enter a loop, checking the websites defined in `config.json` at the interval specified in `agency.py` (`MONITOR_INTERVAL_SECONDS`).
    *   For each website, it runs the agency task.
    *   If a change is detected, an alert will be printed to the console, and the stored content in the `data/` directory will be updated.
    *   Press `Ctrl+C` to stop the script.

## Customization & Extension

*   **Monitoring Interval:** Change `MONITOR_INTERVAL_SECONDS` in `agency.py`.
*   **Fetching Method:** Modify the `FetchContentTool` in `WebsiteMonitor/tools.py` to use `selenium` or `playwright` if needed.
*   **Comparison Logic:** Enhance the `CompareAndPersistTool` in `WebsiteMonitor/tools.py`.
*   **Notifications:** Enhance the `NotificationTool` in `WebsiteMonitor/tools.py`.
*   **Agent Instructions:** Modify `WebsiteMonitor/instructions.md` or the instructions within `MonitorCEO/MonitorCEO.py`.
*   **LLM:** Configure specific LLMs for agents or the agency in `MonitorCEO.py`, `WebsiteMonitor.py`, or `agency.py` if you don't want to use the default OpenAI configuration. 