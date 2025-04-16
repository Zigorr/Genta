# agency.py (main script)
import os
import time
import json
import agency_swarm
from dotenv import load_dotenv
from agency_swarm import Agency
from agency_swarm import set_openai_key

# Import agents from their folders
from MonitorCEO import MonitorCEO
from WebsiteMonitor import WebsiteMonitor

# --- Configuration & Globals ---
load_dotenv(override=True)
# CONFIG_FILE = 'config.json' # No longer reading from config file
MONITOR_INTERVAL_SECONDS = 5 # Check every 5 seconds

# --- LLM Configuration Check ---
set_openai_key(os.getenv("OPENAI_API_KEY"))
# --- Instantiate Agents ---
monitor_ceo = MonitorCEO()
monitor_worker = WebsiteMonitor()

# --- Define Agency ---

agency = Agency(
    agency_chart=[
        monitor_ceo, # CEO is the entry point
        [monitor_ceo, monitor_worker], # CEO can delegate to worker
    ],
    # shared_instructions="./agency_manifesto.md", # Optional shared instructions
)

# --- Main Monitoring Section ---

if __name__ == "__main__":
    print("--- Website Content Monitor Agency Initializing --- ")
    try:
        print(f"--- Using agency-swarm version: {agency_swarm.__version__} ---")
    except AttributeError:
         print("--- Could not determine agency-swarm version. ---")

    # --- Get Target URL and Selector from User ---
    target_url = ""
    while not target_url:
        target_url = input("Enter the full URL to monitor (e.g., https://example.com): ").strip()
        if not target_url:
            print("URL cannot be empty.")

    target_selector = ""
    while not target_selector:
        target_selector = input("Enter the CSS selector for the content to monitor (e.g., body > div > p): ").strip()
        if not target_selector:
            print("CSS selector cannot be empty.")

    print(f"\nMonitoring URL: {target_url}")
    print(f"Using Selector: {target_selector}")
    print(f"Check Interval: {MONITOR_INTERVAL_SECONDS} seconds")
    print("Press Ctrl+C to stop.")
    print("-----------------------------------------------------")

    # --- Monitoring Loop ---
    while True:
        print(f"\n--- Running Check at {time.strftime('%Y-%m-%d %H:%M:%S')} --- ({target_url})" )

        # Construct the task message for the agency
        task_message = (
            f"Please monitor the website for changes.\n"
            f"URL: {target_url}\n"
            f"CSS Selector: {target_selector}"
        )

        try:
            # Run the agency for the specified target
            result = agency.get_completion(task_message)
            print(f"\n>>> Monitoring Task Result: {result}")

        except Exception as e:
            print(f"!!! Error running agency for {target_url}: {e}")
            import traceback
            traceback.print_exc()

        print(f"\n--- Check Complete. Waiting for {MONITOR_INTERVAL_SECONDS} seconds... ---")
        time.sleep(MONITOR_INTERVAL_SECONDS) 