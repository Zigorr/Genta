# agency.py

import os
from app import create_app # Import the app factory
from flask_bootstrap import Bootstrap

# Get config name from environment or use default
# This is mainly for the __main__ block below
config_name = os.getenv('FLASK_ENV') or 'default'

# Create app instance using the factory for potential script usage
# Note: Gunicorn uses wsgi.py, not this instance directly
app = create_app(config_name)

# Initialize Flask-Bootstrap
Bootstrap(app)

# --- Main Entry Point --- (For running with 'python agency.py')
if __name__ == "__main__":
    print(f"--- Starting Flask Development Server (Config: {config_name}) ---")
    print("--- Using Flask's built-in server (Werkzeug) - For development ONLY ---")
    # Pass host/port from config or default here if needed, but app.run defaults work
    # app.run() will use DEBUG setting from the loaded config
    app.run() # host and port can be configured further if needed

'''
# --- OLD CODE REMOVED ---
# (All the Flask app setup, blueprint registration, route definitions etc.
#  are now handled within app/__init__.py's create_app factory)
''' 