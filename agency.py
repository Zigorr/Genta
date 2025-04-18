# agency.py (main script)
import os
import sys
import time
import gradio as gr
import agency_swarm
from dotenv import load_dotenv
from agency_swarm import Agency
from agency_swarm import set_openai_key

# Add the current directory to Python path (like SMM)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import agents using SMM pattern
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# --- Configuration & Globals ---
load_dotenv(override=True) # Still useful for local development

# --- LLM Configuration Check ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY environment variable not found.")
    print("Please ensure it is set in your deployment environment (e.g., Railway Variables) or local .env file.")
    sys.exit(1) # Exit if key is not found
else:
    try:
        set_openai_key(api_key)
        print("OpenAI API Key loaded and set successfully.")
    except Exception as e:
        print(f"Error setting OpenAI API key: {e}")
        sys.exit(1)


# --- Instantiate Agents ---
# This code will only run if the API key was successfully set above
print("Initializing agents...")
try:
    monitor_ceo = MonitorCEO()
    monitor_worker = WebsiteMonitor()
    print("Agents initialized successfully.")
except Exception as e:
    # This might catch other agent init errors, but the key error should be caught above.
    print(f"Error initializing agents: {e}")
    sys.exit(1) # Exit if agents fail to initialize

# --- Define Agency ---
# This code will only run if agents were initialized successfully
print("Creating agency structure...")
agency = Agency(
    agency_chart=[
        monitor_ceo, # CEO is the entry point
        [monitor_ceo, monitor_worker], # CEO can delegate to worker
    ],
    shared_instructions='agency_manifesto.md', # Use manifesto file
    # max_prompt_tokens=12000 # Optional: Set token limit if needed
)
print("Agency structure created successfully.")


# --- Gradio Interface (using built-in demo) ---
if __name__ == "__main__":
    print("--- Starting Gradio Web Interface (Agency Swarm Demo) ---")
    try:
        print(f"--- Using agency-swarm version: {agency_swarm.__version__} ---")
    except AttributeError:
         print("--- Could not determine agency-swarm version. ---")

    # Launch the built-in Gradio demo
    # Railway uses PORT environment variable for the internal port
    server_port = int(os.getenv("PORT", 7860)) # Default to 7860 if PORT not set
    print(f"Launching Gradio on internal port: {server_port}")
    print("Gradio launch skipped for diagnostics, sleeping for 10 minutes...")
    time.sleep(600) # Sleep for 600 seconds (10 minutes)
    print("Sleep finished.") # You likely won't see this if it works

    agency.demo_gradio(server_name="0.0.0.0", server_port=server_port, share=True)

    print("--- Gradio Interface Closed ---") 