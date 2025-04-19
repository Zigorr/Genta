# wsgi.py
import os
from app import create_app # Import the factory function

# Determine the config name from environment variable or default to production
config_name = os.getenv('FLASK_ENV') or 'production'

# Create the application instance using the factory
application = create_app(config_name)

# Optional: Add any WSGI middleware here if needed
# from werkzeug.middleware.dispatcher import DispatcherMiddleware
# application = DispatcherMiddleware(application, { ... }) 