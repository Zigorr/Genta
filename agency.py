# agency.py (main script)
import os
import sys
import json
import re
import atexit
from datetime import timedelta

# Flask Imports
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, g, session
from flask_login import LoginManager, login_required, current_user # Removed unused imports
from werkzeug.middleware.proxy_fix import ProxyFix # Import ProxyFix
# Removed werkzeug security imports, handled in Auth

# Flask-Dance imports removed, handled in Auth
# from flask_dance.contrib.google import make_google_blueprint, google
# from flask_dance.consumer import oauth_authorized, oauth_error

# Agency Swarm Imports
from agency_swarm import Agency
from agency_swarm import set_openai_key
from dotenv import load_dotenv

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import local modules
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor
from Database.database_manager import init_db, close_db_pool, User # Only User needed here potentially for type hints, others used in Auth
from Auth import create_auth_blueprint # Import the blueprint factory

# --- Configuration & Constants ---
load_dotenv(override=True)
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "a-secure-default-secret-key-for-dev-change-me")

# --- LLM Configuration Check ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY environment variable not found.", file=sys.stderr)
    sys.exit(1)
else:
    try:
        set_openai_key(api_key)
        print("OpenAI API Key loaded and set successfully.")
    except Exception as e:
        print(f"Error setting OpenAI API key: {e}", file=sys.stderr)
        sys.exit(1)

# --- Flask App Setup (Main App) ---
app = Flask(__name__)

# Apply ProxyFix BEFORE other configurations that might depend on URL scheme
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = FLASK_SECRET_KEY

# Configure session timeout
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# OAuth Configuration REMOVED (Handled in Auth blueprint)
# app.config["GOOGLE_OAUTH_CLIENT_ID"] = ...
# app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = ...
# if os.getenv("OAUTHLIB_INSECURE_TRANSPORT") == "1": ...

# --- Login Manager Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
# login_manager.login_view = 'login' # Moved to create_auth_blueprint

# --- Create and Register Auth Blueprint ---
auth_bp = create_auth_blueprint(login_manager) # Pass login_manager
app.register_blueprint(auth_bp) # Register the auth blueprint

# --- Database Initialization ---
with app.app_context():
    init_db()

# --- Shutdown Hook ---
atexit.register(close_db_pool)

# --- User Management (REMOVED - Handled in Auth & Database modules) ---
# @login_manager.user_loader
# def load_user(user_id): ...

# @login_manager.unauthorized_handler
# def unauthorized(): ...

# --- Authentication Routes (REMOVED - Handled in Auth blueprint) ---
# @app.route('/login', ...)
# def login(): ...
#
# @app.route('/register', ...)
# def register(): ...
#
# @app.route('/logout')
# def logout(): ...

# --- Google OAuth Handlers (REMOVED - Handled in Auth blueprint) ---
# @app.route("/google_logged_in")
# @oauth_authorized.connect_via(google_bp)
# def google_logged_in_handler(blueprint, token): ...
#
# @oauth_error.connect_via(google_bp)
# def google_oauth_error(blueprint, error, ...): ...

# --- Main Application Routes ---

@app.route('/')
@login_required # Still use login_required decorator
def index():
    # Render the main chat interface template
    return render_template('chat.html')

# --- Instantiate Agents & Agency (Keep in main app) ---
print("Initializing agents...")
try:
    monitor_ceo = MonitorCEO()
    monitor_worker = WebsiteMonitor()
    print("Agents initialized successfully.")
except Exception as e:
    print(f"Error initializing agents: {e}", file=sys.stderr)
    sys.exit(1)

print("Creating agency structure...")
agency = Agency(
    agency_chart=[
        monitor_ceo,
        [monitor_ceo, monitor_worker],
    ],
    shared_instructions='agency_manifesto.md', # Make sure this file exists or remove
)
print("Agency structure created successfully.")

# --- API Endpoint for Chat (Keep in main app) ---
@app.route('/api/chat', methods=['POST'])
@login_required # Protect the API endpoint
def chat_api():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    message = data.get('message')

    if not message:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    print(f"API received message from user {current_user.id}: {message}") # Use current_user
    try:
        response_text = agency.get_completion(message)
        print(f"API sending response: {response_text}")
        return jsonify({"response": response_text})

    except Exception as e:
        print(f"Error during agency completion via API: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc() # Log full traceback to server logs
        return jsonify({"error": f"An internal error occurred: {e}"}), 500

# --- Main Entry Point --- (Keep in main app)
if __name__ == "__main__":
    print("--- Starting Flask Development Server ---")
    print("--- Using Flask's built-in server (Werkzeug) - For development ONLY ---")
    # Note: debug=True enables auto-reloading and debugger
    # Use host='0.0.0.0' to be accessible on the network
    app.run(debug=True, host='0.0.0.0', port=5000) 