# wsgi.py
import os
from app import create_app # Import the factory function
# Removed load_dotenv here - should be handled by Railway env vars
# from dotenv import load_dotenv

# load_dotenv() # Removed

# --- DEBUGGING --- 
DATABASE_URL_FROM_ENV = os.getenv('DATABASE_URL')
print(f"DEBUG: DATABASE_URL from environment in wsgi.py: {DATABASE_URL_FROM_ENV}", flush=True)
# --- END DEBUGGING ---

# Determine the config name from environment variable or default to production
config_name = os.getenv('FLASK_ENV') or 'production'

# Check if DATABASE_URL is set, otherwise maybe default to SQLite? 
# Although init_db has its own default logic.
if not DATABASE_URL_FROM_ENV:
    print("WARNING: DATABASE_URL environment variable not set in wsgi.py.", flush=True)

# Create the application instance using the factory
application = create_app(config_name)

# Optional: Add any WSGI middleware here if needed
# from werkzeug.middleware.dispatcher import DispatcherMiddleware
# application = DispatcherMiddleware(application, { ... }) 