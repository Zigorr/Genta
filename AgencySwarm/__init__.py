# AgencySwarm/__init__.py

import sys
import traceback
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

# Agency Swarm Imports
from agency_swarm import Agency

# Import agent classes (adjust path if needed, assumes they are at the root)
# Change to direct import if modules are siblings
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# Import the blueprint (now named _api_bp) from the main module file and export with desired name
from .AgencySwarm import _api_bp as agency_api_bp

# --- Agency Setup ---
# Global variable to hold the initialized agency instance
# This avoids re-initializing agents on every request
_agency_instance = None

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

@agency_api_bp.route('/chat', methods=['POST'])
@login_required # Protect the API endpoint
def chat_api():
    agency = create_agency() # Get or create the agency instance
    if not agency:
         return jsonify({"error": "Agency failed to initialize. Check server logs."}), 500

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    message = data.get('message')

    if not message:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    print(f"API received message from user {current_user.id}: {message}")
    try:
        # Get completion from the agency
        response_text = agency.get_completion(message)
        print(f"API sending response: {response_text}")
        return jsonify({"response": response_text})

    except Exception as e:
        print(f"Error during agency completion via API: {e}", file=sys.stderr)
        traceback.print_exc() # Log full traceback
        return jsonify({"error": f"An internal error occurred: {e}"}), 500 