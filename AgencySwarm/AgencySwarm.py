# AgencySwarm/AgencySwarm.py

import sys
import traceback
import io                 # Added for capturing stdout
import contextlib         # Added for redirecting stdout
import datetime # Added
from datetime import timezone, timedelta # Added
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
import tiktoken

# Agency Swarm Imports
from agency_swarm import Agency

# Import agent classes (adjust path if needed, assumes they are at the root)
# If agents are moved into AgencySwarm folder, change imports
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# Import database functions
from Database.database_manager import get_user_token_details, update_token_usage, add_chat_message, reset_tokens

# Define the Blueprint for API routes related to the agency
# Using url_prefix='/api' will make routes like /api/chat
# Renamed to _api_bp internally, expose via __init__.py
# Rename blueprint to avoid potential conflicts
_api_bp = Blueprint('agency_api', __name__, url_prefix='/api')

# --- Agency Setup ---
# Global variable to hold the initialized agency instance
# This avoids re-initializing agents on every request
_agency_instance = None
# Global variable for tokenizer encoding
_tokenizer_encoding = None

def get_tokenizer_encoding():
    """Initializes and returns the tiktoken encoding."""
    global _tokenizer_encoding
    if _tokenizer_encoding is None:
        try:
            # Use a common model for estimation. Change if you know the specific model used by agency-swarm.
            _tokenizer_encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except Exception as e:
            print(f"Error initializing tiktoken encoder: {e}", file=sys.stderr)
            _tokenizer_encoding = None # Ensure it's None if failed
    return _tokenizer_encoding

def create_agency():
    """Initializes and returns the Agency Swarm Agency object."""
    global _agency_instance
    if _agency_instance is None:
        print("Initializing agents...")
        try:
            monitor_ceo = MonitorCEO()
            monitor_worker = WebsiteMonitor()
            print("Agents initialized successfully.")

            print("Creating agency structure...")
            _agency_instance = Agency(
                agency_chart=[
                    monitor_ceo,
                    [monitor_ceo, monitor_worker],
                ],
                # Check path relative to project root where app runs
                shared_instructions='agency_manifesto.md',
            )
            print("Agency structure created successfully.")

        except FileNotFoundError:
            print("Error: agency_manifesto.md not found. Please ensure it exists.", file=sys.stderr)
            # Fallback or specific handling if manifesto is optional/critical
            _agency_instance = Agency( # Initialize without manifesto if necessary
                 agency_chart=[
                    monitor_ceo,
                    [monitor_ceo, monitor_worker],
                ]
            )
            print("Agency structure created (without shared instructions).")

        except Exception as e:
            print(f"Fatal Error initializing agents or agency structure: {e}", file=sys.stderr)
            traceback.print_exc()
            # Depending on severity, you might want to exit or prevent app startup
            # For now, we'll let it continue but _agency_instance might remain None
            # Returning None or raising an exception might be better.
            return None # Indicate failure

    return _agency_instance

# --- API Endpoint(s) ---

# Add an explicit, unique endpoint name
@_api_bp.route('/chat', methods=['POST'], endpoint='agency_chat')
@login_required # Protect the API endpoint
def chat_api():
    user_id = current_user.id
    token_details = get_user_token_details(user_id)
    encoding = get_tokenizer_encoding()

    if not encoding:
         return jsonify({"error": "Token processing unavailable. Please try again later."}), 500
    if not token_details:
         print(f"Error: Could not retrieve token details for logged-in user {user_id}")
         return jsonify({"error": "Could not verify user usage details."}), 500

    # --- Check and Apply Token Reset --- 
    if not token_details['is_subscribed']:
        last_reset_time = token_details.get('last_token_reset')
        reset_interval_minutes = current_app.config.get('TOKEN_RESET_INTERVAL_MINUTES', 5)
        
        # Ensure last_reset_time is timezone-aware (it should be if stored as TIMESTAMPTZ)
        # If it's missing or None (e.g., old user row before column added), force reset
        needs_reset = False
        if last_reset_time:
            now_utc = datetime.datetime.now(timezone.utc)
            time_since_reset = now_utc - last_reset_time
            if time_since_reset > timedelta(minutes=reset_interval_minutes):
                needs_reset = True
        else:
            # No previous reset time found, trigger reset
            needs_reset = True 
            
        if needs_reset:
            print(f"User {user_id} token reset interval ({reset_interval_minutes} min) passed. Resetting tokens.")
            reset_success = reset_tokens(user_id)
            if reset_success:
                # IMPORTANT: Re-fetch details after reset
                print(f"Re-fetching token details for user {user_id} after reset.")
                token_details = get_user_token_details(user_id)
                if not token_details:
                     print(f"Error: Could not re-fetch token details after reset for user {user_id}")
                     # Fail safe? Or proceed assuming reset worked?
                     # Let's return an error to be safe.
                     return jsonify({"error": "Error applying token reset. Please try again."}), 500
            else:
                 print(f"Error: Failed to reset tokens for user {user_id}. Proceeding without reset.")
                 # Decide how to handle - maybe proceed with old token count?
                 # For now, we log the error and continue; the limit check below will use the old count.

    # --- Token Limit Check --- 
    token_limit = current_app.config.get('FREE_TIER_TOKEN_LIMIT', 200)
    if not token_details['is_subscribed']:
        if token_details['tokens_used'] >= token_limit:
            print(f"User {user_id} reached token limit ({token_details['tokens_used']} >= {token_limit})")
            
            # --- Calculate Time Remaining --- 
            time_remaining_str = "soon" # Default message
            next_reset_timestamp_iso = None
            reset_interval_minutes = current_app.config.get('TOKEN_RESET_INTERVAL_MINUTES', 5)
            last_reset_time = token_details.get('last_token_reset')

            if last_reset_time:
                # Ensure last_reset_time is offset-aware UTC
                if last_reset_time.tzinfo is None:
                     # If somehow it's naive, assume UTC (though TIMESTAMPTZ should prevent this)
                     last_reset_time = last_reset_time.replace(tzinfo=timezone.utc)
                
                next_reset_time = last_reset_time + timedelta(minutes=reset_interval_minutes)
                now_utc = datetime.datetime.now(timezone.utc)
                time_remaining = next_reset_time - now_utc
                next_reset_timestamp_iso = next_reset_time.isoformat()

                if time_remaining.total_seconds() > 0:
                    total_seconds = int(time_remaining.total_seconds())
                    minutes = total_seconds // 60
                    seconds = total_seconds % 60
                    if minutes > 0:
                        time_remaining_str = f"in approximately {minutes} minute(s) and {seconds} second(s)"
                    else:
                        time_remaining_str = f"in approximately {seconds} second(s)"
                else:
                    time_remaining_str = "very shortly (on your next request)"
            else:
                # Should ideally not happen if column has default, but handle anyway
                time_remaining_str = "on your next request"

            limit_message = f"You have reached your free token limit of {token_limit}. Your tokens will reset {time_remaining_str}."
            
            return jsonify({
                "limit_reached": True,
                "message": limit_message,
                "next_reset_at": next_reset_timestamp_iso # Optional: send timestamp for potential frontend timer
            }), 403

    # --- Proceed with Agency Interaction ---
    agency = create_agency()
    if not agency:
         return jsonify({"error": "Agency failed to initialize. Check server logs."}), 500

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    message = data.get('message')

    if not message:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    # --- Log User Message ---
    try:
        add_chat_message(user_id, 'user', message)
    except Exception as log_e: # Catch potential logging errors
        print(f"Error logging user message: {log_e}", file=sys.stderr)
        # Decide if this should prevent continuing? Maybe not.

    print(f"API received message from user {user_id}: {message}")
    response_payload = {}
    captured_steps = ""
    final_response_text = ""
    error_occurred = False
    error_message = ""

    try:
        # --- Token Counting ---
        prompt_tokens = len(encoding.encode(message))
        print(f"User {user_id} - Prompt tokens: {prompt_tokens}")

        # --- Capture stdout during agency completion ---
        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                final_response_text = agency.get_completion(message)
        finally:
            captured_steps = stdout_capture.getvalue()
            # Optional: Print captured steps to actual console for debugging if needed
            # print("--- Captured Steps ---")
            # print(captured_steps)
            # print("--- End Captured Steps ---")

        # --- Token Counting (Completion) ---
        completion_tokens = len(encoding.encode(final_response_text))
        total_tokens = prompt_tokens + completion_tokens
        print(f"User {user_id} - Completion tokens: {completion_tokens}, Total: {total_tokens}")

        # --- Update Usage ---
        # Update usage only if not subscribed
        if not token_details['is_subscribed']:
            success = update_token_usage(user_id, total_tokens)
            if not success:
                # Log error but potentially still return response to user?
                print(f"Warning: Failed to update token usage for user {user_id}")
            else:
                 print(f"User {user_id} - Updated token usage by {total_tokens}")

        response_payload = {
            "response": final_response_text,
            "steps": captured_steps,
            "limit_reached": False
        }

        # --- Log Agent Response ---
        try:
            if captured_steps.strip(): # Log steps if captured
                add_chat_message(user_id, 'system', f"--- Agent Steps ---\n{captured_steps}")
            add_chat_message(user_id, 'assistant', final_response_text)
        except Exception as log_e: 
             print(f"Error logging agent response: {log_e}", file=sys.stderr)

    except Exception as e:
        error_occurred = True
        error_message = f"An internal error occurred: {e}"
        print(f"Error during agency completion via API: {e}", file=sys.stderr)
        traceback.print_exc()
        response_payload = {"error": error_message}
        # --- Log Error Message ---
        try:
            add_chat_message(user_id, 'error', error_message)
        except Exception as log_e:
            print(f"Error logging error message: {log_e}", file=sys.stderr)

    # --- Return JSON Response ---
    status_code = 500 if error_occurred else 200
    print(f"API sending response (Status: {status_code}): {response_payload.get('response', response_payload.get('error'))}")
    return jsonify(response_payload), status_code 