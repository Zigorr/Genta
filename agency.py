# agency.py (main script)
import os
import sys  # Added sys
import time # Keep time for potential use, though loop removed
# import json # No longer directly used here
# import threading # Removed threading
import gradio as gr # Keep gradio for demo_gradio
import agency_swarm # Keep agency_swarm
from dotenv import load_dotenv
from agency_swarm import Agency
from agency_swarm import set_openai_key

# Add the current directory to Python path (like SMM)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import agents using SMM pattern
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# --- Configuration & Globals ---
load_dotenv(override=True)
# MONITOR_INTERVAL_SECONDS = 5 # Interval managed by user interaction/task frequency now

# --- LLM Configuration Check ---
if not os.getenv("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY not found in .env file.")
    # Potentially exit or raise error
else:
    set_openai_key(os.getenv("OPENAI_API_KEY"))
    print("OpenAI API Key loaded.")

# --- Instantiate Agents ---
print("Initializing agents...")
try:
    monitor_ceo = MonitorCEO()
    monitor_worker = WebsiteMonitor()
    print("Agents initialized successfully.")
except Exception as e:
    print(f"Error initializing agents: {e}")
    # Potentially exit or raise error

# --- Define Agency ---
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

# --- Remove Old Monitoring State/Functions --- 
# monitoring_thread = None
# is_monitoring = False
# logs = ["--- Waiting to start monitoring ---"]
# stop_event = threading.Event()
# def log_message(message):
# def monitoring_loop(url, selector):
# def start_monitoring(url, selector):
# def stop_monitoring():
# def get_logs():

# --- Gradio Interface (using built-in demo) ---
if __name__ == "__main__":
    print("--- Starting Gradio Web Interface (Agency Swarm Demo) ---")
    try:
        print(f"--- Using agency-swarm version: {agency_swarm.__version__} ---")
    except AttributeError:
         print("--- Could not determine agency-swarm version. ---")

    # Launch the built-in Gradio demo
    agency.demo_gradio(server_name="0.0.0.0", share=False)

    print("--- Gradio Interface Closed ---") 