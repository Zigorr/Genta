# app/__init__.py
import os
import sys
import atexit
import logging

from flask import Flask, render_template, request # Keep request import here
from flask_login import LoginManager, login_required, current_user # Keep login_required for index, Add current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from agency_swarm import set_openai_key
from flask_bootstrap import Bootstrap # Import Bootstrap
from flask_mail import Mail # Import Mail

# Import config
from config import config # Use the dictionary defined in config.py

# Import modules/blueprints
# Assuming Database, Auth, AgencySwarm are siblings to the 'app' directory
# If they are inside 'app', change the import path
# Import directly from database_manager again
# Use correct function names for DB pool
# Removed test_db_connection as it doesn't exist
from Database.database_manager import (
    init_connection_pool, close_connection_pool, init_db, get_chat_history,
    get_conversations_for_user # Import get_conversations_for_user
)
from Auth import create_auth_blueprint
from AgencySwarm import agency_api_bp # Import the renamed blueprint export
from UserSettings import settings_bp # Import the new blueprint
from flask_dance.contrib.google import make_google_blueprint

# Initialize extensions (outside factory to make them accessible)
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # The endpoint name for the login route
mail = Mail() # Initialize Mail object


def create_app(config_name='default'):
    """Application factory function."""
    # Explicitly set template_folder and static_folder relative to the app package directory
    # Assuming 'static' and 'templates' are siblings to the 'app' directory (i.e., in the project root)
    app = Flask(__name__,
                instance_relative_config=False,
                template_folder='../templates',
                static_folder='../static')

    # Load configuration
    cfg = config[config_name]
    app.config.from_object(cfg)
    cfg.init_app(app) # Perform config-specific initialization

    # Apply ProxyFix BEFORE other configurations that might depend on URL scheme
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Initialize extensions with the app
    login_manager.init_app(app)
    Bootstrap(app) # Initialize Bootstrap here
    mail.init_app(app) # Initialize Mail with the app

    # Set OpenAI API Key (check moved to config.init_app)
    if app.config.get('OPENAI_API_KEY'):
        try:
            set_openai_key(app.config['OPENAI_API_KEY'])
            print("OpenAI API Key set successfully.")
        except Exception as e:
            print(f"Error setting OpenAI API key from config: {e}", file=sys.stderr)
            # Depending on severity, might want to exit or raise exception
    else:
        print("ERROR: OpenAI API Key not found in config.", file=sys.stderr)

    # Initialize Database within app context
    with app.app_context():
        init_connection_pool() # Use correct function name
        init_db() # Call init_db to ensure tables are created/updated
        # test_db_connection() # Removed call to non-existent function
        print("Database pool initialized.") # Simplified message

    # Register blueprints
    auth_bp = create_auth_blueprint(login_manager) # Pass login_manager
    app.register_blueprint(auth_bp)
    app.register_blueprint(agency_api_bp)
    app.register_blueprint(settings_bp) # Register the new blueprint

    # Google OAuth Blueprint
    # Ensure necessary environment variables are set
    google_client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')

    if not google_client_id or not google_client_secret:
        print("Google OAuth credentials not found in environment variables. Google login will not work.")
        google_bp = None # Indicate that Google login is unavailable
    else:
        google_bp = make_google_blueprint(
            client_id=google_client_id,
            client_secret=google_client_secret,
            scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
            redirect_to="auth.google_login" # Redirect to the processing route after Google auth
        )

    if google_bp:
        app.register_blueprint(google_bp, url_prefix="/login") # Google login starts at /login/google

    # Modified index route
    @app.route('/')
    @login_required
    def index():
        try:
            # Fetch the list of conversations for the sidebar
            conversations = get_conversations_for_user(current_user.id)
            # Initial history is empty; messages loaded via JS or specific route
            chat_history = []
            # Render the main chat interface template, passing conversations and empty history
            return render_template('chat.html', conversations=conversations, history=chat_history)
        except Exception as e:
            # Explicitly log any exception occurring in this route
            app.logger.error(f"Error rendering index route: {e}", exc_info=True)
            # Reraise the exception or return a generic error response
            # Re-raising might be better for seeing the original 500 error page
            # raise
            # Or return a custom error page/message:
            return "An internal error occurred while loading the page.", 500

    # Register shutdown hook
    atexit.register(close_connection_pool) # Use correct function name

    # Request Teardown
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        # This function is called when the app context is torn down,
        # which happens after a request or when the app shuts down.
        # *** DO NOT close the pool here - it should persist for the worker life ***
        # close_connection_pool() # REMOVED
        pass # Can remove the function entirely if nothing else needs teardown
        # app.logger.info("Database pool closed for app context.") # Optional: Log pool closure

    # Error Handling
    @app.errorhandler(404)
    def page_not_found(e):
        from flask import request # Import request explicitly here for clarity/linter
        # You can render a template for 404 errors
        # return render_template('404.html'), 404
        app.logger.warning(f"404 Not Found: {e} at {request.url}") 
        return "Page Not Found", 404 # Simple text response for now

    return app 