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
from collections import OrderedDict # Import OrderedDict for LRU cache behaviour
import threading # Import threading for Lock

# Agency Swarm Imports
from agency_swarm import Agency

# Import agent classes (adjust path if needed, assumes they are at the root)
# If agents are moved into AgencySwarm folder, change imports
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# Import database functions
from Database.database_manager import (
    get_user_token_details, update_token_usage, add_chat_message, reset_tokens,
    create_conversation, check_conversation_owner, get_chat_history # Add new imports
)

# Define the Blueprint for API routes related to the agency
# Using url_prefix='/api' will make routes like /api/chat
# Renamed to _api_bp internally, expose via __init__.py
# Rename blueprint to avoid potential conflicts
_api_bp = Blueprint('agency_api', __name__, url_prefix='/api')

# --- Agency Setup ---
# Global cache for agency instances per conversation_id (LRU Cache)
# Keys: conversation_id, Values: Agency instance
_agency_cache = OrderedDict()
MAX_CACHE_SIZE = 50 # Max number of agency instances to keep in memory per worker
_cache_lock = threading.Lock() # Add a lock for cache access and agent usage

# Global variable for tokenizer encoding (can still be shared)
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

# Renamed from create_agency - This now BUILDS a NEW instance every time it's called.
def _build_new_agency(conversation_id):
    """Builds and returns a NEW Agency Swarm Agency object for each call."""
    print(f"Building NEW agency instance for conversation {conversation_id}...")
    try:
        monitor_ceo = MonitorCEO()
        monitor_worker = WebsiteMonitor()
        print("Agents initialized successfully.")

        print("Creating agency structure...")
        # Create the new agency instance directly
        agency = Agency(
            agency_chart=[
                monitor_ceo,
                [monitor_ceo, monitor_worker],
            ],
            # Check path relative to project root where app runs
            shared_instructions='agency_manifesto.md',
        )
        print(f"Agency structure created successfully for conversation {conversation_id}.")
        return agency # Return the newly created instance

    except FileNotFoundError:
        print(f"Warning: agency_manifesto.md not found for conversation {conversation_id}. Creating without.", file=sys.stderr)
        # Create without manifesto
        agency = Agency(
             agency_chart=[
                monitor_ceo,
                [monitor_ceo, monitor_worker],
            ]
        )
        print(f"Agency structure created (no manifesto) for conversation {conversation_id}.")
        return agency # Return the newly created instance

    except Exception as e:
        print(f"Fatal Error initializing agents or agency structure: {e}", file=sys.stderr)
        traceback.print_exc()
        return None # Indicate failure

def get_or_create_agency(conversation_id):
    """Gets an agency instance from cache or creates a new one (Thread-Safe)."""
    global _agency_cache
    with _cache_lock: # Acquire lock for reading/writing cache
        if conversation_id in _agency_cache:
            _agency_cache.move_to_end(conversation_id)
            print(f"Reusing cached agency instance for conversation {conversation_id}.")
            return _agency_cache[conversation_id]
        else:
            if len(_agency_cache) >= MAX_CACHE_SIZE:
                oldest_convo_id, _ = _agency_cache.popitem(last=False)
                print(f"Cache full. Evicted agency instance for conversation {oldest_convo_id}.")
            # Build happens inside the lock to prevent multiple builds for the same new ID
            new_agency = _build_new_agency(conversation_id)
            if new_agency:
                _agency_cache[conversation_id] = new_agency
                print(f"Cached new agency instance for conversation {conversation_id}.")
            return new_agency

# --- API Endpoint(s) ---

@_api_bp.route('/chat', methods=['POST'], endpoint='agency_chat')
@login_required
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

    # --- Get Request Data ---
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    message = data.get('message')
    conversation_id = data.get('conversation_id') # Get conversation_id from request

    if not message:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    # --- Validate or Create Conversation --- 
    is_new_conversation = False
    if conversation_id:
        try:
            conversation_id = int(conversation_id) # Ensure it's an integer
            if not check_conversation_owner(conversation_id, user_id):
                 print(f"Warning: User {user_id} attempted to access conversation {conversation_id} they don't own. Starting new conversation.")
                 conversation_id = None # Treat as invalid
            else:
                 print(f"Continuing conversation {conversation_id} for user {user_id}")
        except (ValueError, TypeError):
             print(f"Warning: Invalid conversation_id format received: {conversation_id}. Starting new conversation.")
             conversation_id = None

    if not conversation_id:
        print(f"No valid conversation_id provided. Creating new conversation for user {user_id}.")
        conversation_id = create_conversation(user_id)
        if not conversation_id:
             print(f"ERROR: Failed to create a new conversation for user {user_id}.")
             return jsonify({"error": "Failed to start a new chat session."}), 500
        print(f"Started new conversation {conversation_id} for user {user_id}.")
        is_new_conversation = True # Flag that a new convo was created

    # --- Log User Message (with conversation_id) ---
    try:
        # Pass conversation_id to add_chat_message
        add_chat_message(user_id, conversation_id, 'user', message)
    except Exception as e:
        # Log error but continue for now
        print(f"Error saving user message for user {user_id}, convo {conversation_id}: {e}", file=sys.stderr)
        traceback.print_exc()

    # --- Proceed with Agency Interaction --- 
    # Get agency from cache or create a new one for this conversation
    agency = get_or_create_agency(conversation_id)

    if not agency:
         # Log error with conversation ID if available
         print(f"ERROR: Agency failed to initialize for request (convo: {conversation_id}, user: {user_id}).")
         return jsonify({
             "conversation_id": conversation_id,
             "error": "Agency failed to initialize or retrieve. Check server logs."
             }), 500

    print(f"Using agency for convo {conversation_id}. Processing message from user {user_id}.")
    response_payload = {}
    captured_steps = ""
    final_response_text = ""
    error_occurred = False
    error_message = ""

    try:
        # --- Token Counting (Prompt) ---
        prompt_tokens = len(encoding.encode(message))
        print(f"User {user_id} - Prompt tokens: {prompt_tokens}")

        # --- Capture stdout during agency completion ---
        stdout_capture = io.StringIO()
        try:
            # Acquire lock specifically around using the potentially shared agency instance
            with _cache_lock:
                print(f"Lock acquired for agency completion (convo: {conversation_id})")
                with contextlib.redirect_stdout(stdout_capture):
                    # *** CRITICAL: Pass the message to the cached/retrieved agency instance ***
                    final_response_text = agency.get_completion(message)
            print(f"Lock released after agency completion (convo: {conversation_id})")
        finally:
            captured_steps = stdout_capture.getvalue()
            # Optional: Print captured steps to actual console for debugging if needed
            # print("--- Captured Steps ---")
            # print(captured_steps)
            # print("--- End Captured Steps ---")

        # --- Token Counting (Completion) & Update Usage ---
        completion_tokens = len(encoding.encode(final_response_text))
        total_tokens = prompt_tokens + completion_tokens
        print(f"User {user_id} - Completion tokens: {completion_tokens}, Total: {total_tokens}")

        # Update usage only if not subscribed
        if not token_details['is_subscribed']:
            success = update_token_usage(user_id, total_tokens)
            if not success:
                # Log error but potentially still return response to user?
                print(f"Warning: Failed to update token usage for user {user_id}")
            else:
                 print(f"User {user_id} - Updated token usage by {total_tokens}")

        # --- Prepare Response Payload --- 
        response_payload = {
            "conversation_id": conversation_id, # Return the conversation ID
            "is_new_conversation": is_new_conversation, # Indicate if a new one was made
            "response": final_response_text,
            "steps": captured_steps,
            "limit_reached": False
        }

        # --- Log Agent Response (with conversation_id) ---
        try:
            # COMMENTED OUT: Don't save system messages (agent steps)
            # if captured_steps.strip(): add_chat_message(user_id, conversation_id, 'system', f"--- Agent Steps ---\n{captured_steps}")
            
            # Save assistant response
            add_chat_message(user_id, conversation_id, 'assistant', final_response_text)
        except Exception as log_e: print(f"Error logging agent response for convo {conversation_id}: {log_e}", file=sys.stderr)

    except Exception as e:
        error_occurred = True
        error_message = f"An internal error occurred processing your request."
        print(f"Error during agency completion for convo {conversation_id}: {e}", file=sys.stderr)
        traceback.print_exc()
        response_payload = {"conversation_id": conversation_id, "error": error_message}
        # --- Log Error Message (with conversation_id) ---
        try:
            # COMMENTED OUT: Don't save error messages to chat history
            # add_chat_message(user_id, conversation_id, 'error', f"Internal Error: {e}")
            pass # No action needed here now
        except Exception as log_e: print(f"Error logging error message for convo {conversation_id}: {log_e}", file=sys.stderr)

    # --- Return JSON Response ---
    status_code = 500 if error_occurred else 200
    print(f"API sending response for convo {conversation_id} (Status: {status_code})") # Log convo ID
    return jsonify(response_payload), status_code 

# --- Endpoint to get messages for a conversation --- 
@_api_bp.route('/conversations/<int:conversation_id>/messages', methods=['GET'], endpoint='get_conversation_messages')
@login_required
def get_messages_api(conversation_id):
    user_id = current_user.id
    if not check_conversation_owner(conversation_id, user_id):
        return jsonify({"error": "Conversation not found or access denied"}), 404
    try:
        messages = get_chat_history(conversation_id)
        # Filter messages to include only 'user' and 'assistant' roles
        filtered_messages = [msg for msg in messages if msg[3] in ('user', 'assistant')]
        # Format the filtered messages for easier JS consumption
        formatted_messages = [{'role': msg[3], 'content': msg[4]} for msg in filtered_messages]
        return jsonify(formatted_messages), 200
    except Exception as e:
        print(f"Error fetching messages for conversation {conversation_id}: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({"error": "Failed to retrieve messages"}), 500 