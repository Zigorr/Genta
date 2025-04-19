# AgencySwarm/AgencySwarm.py

import sys
import traceback
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
from Database.database_manager import get_user_token_details, update_token_usage

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
    # --- Token Limit Check ---
    user_id = current_user.id
    token_details = get_user_token_details(user_id)
    token_limit = current_app.config.get('FREE_TIER_TOKEN_LIMIT', 200)
    encoding = get_tokenizer_encoding()

    if not encoding:
         return jsonify({"error": "Token processing unavailable. Please try again later."}), 500

    if token_details and not token_details['is_subscribed']:
        if token_details['tokens_used'] >= token_limit:
            print(f"User {user_id} reached token limit ({token_details['tokens_used']} >= {token_limit})")
            # Return a specific structure indicating limit reached
            return jsonify({
                "limit_reached": True,
                "message": f"You have reached your free token limit of {token_limit}."
            }), 403 # 403 Forbidden is appropriate
    elif not token_details:
         # Should not happen for a logged-in user, but handle defensively
         print(f"Error: Could not retrieve token details for logged-in user {user_id}")
         return jsonify({"error": "Could not verify user usage details."}), 500

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

    print(f"API received message from user {user_id}: {message}")
    try:
        # --- Token Counting ---
        prompt_tokens = len(encoding.encode(message))
        print(f"User {user_id} - Prompt tokens: {prompt_tokens}")

        # Get completion from the agency
        response_text = agency.get_completion(message)

        completion_tokens = len(encoding.encode(response_text))
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

        print(f"API sending response: {response_text}")
        return jsonify({"response": response_text, "limit_reached": False})

    except Exception as e:
        print(f"Error during agency completion via API: {e}", file=sys.stderr)
        traceback.print_exc() # Log full traceback
        return jsonify({"error": f"An internal error occurred: {e}"}), 500 