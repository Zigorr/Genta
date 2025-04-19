# app/__init__.py
import os
import sys
import atexit

from flask import Flask, render_template # Import render_template for index route
from flask_login import LoginManager, login_required # Keep login_required for index
from werkzeug.middleware.proxy_fix import ProxyFix
from agency_swarm import set_openai_key

# Import config
from config import config # Use the dictionary defined in config.py

# Import modules/blueprints
# Assuming Database, Auth, AgencySwarm are siblings to the 'app' directory
# If they are inside 'app', change the import path
# Import directly from database_manager again
from Database.database_manager import init_db, close_db_pool
from Auth import create_auth_blueprint
from AgencySwarm import api_bp as agency_api_bp

# Initialize extensions (outside factory to make them accessible)
login_manager = LoginManager()


def create_app(config_name='default'):
    """Application factory function."""
    app = Flask(__name__, instance_relative_config=False)

    # Load configuration
    cfg = config[config_name]
    app.config.from_object(cfg)
    cfg.init_app(app) # Perform config-specific initialization

    # Apply ProxyFix BEFORE other configurations that might depend on URL scheme
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Initialize extensions with the app
    login_manager.init_app(app)

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
        init_db()

    # Register blueprints
    auth_bp = create_auth_blueprint(login_manager) # Pass login_manager
    app.register_blueprint(auth_bp)
    app.register_blueprint(agency_api_bp)

    # Register simple route for index page
    @app.route('/')
    @login_required
    def index():
        return render_template('chat.html')

    # Register shutdown hook
    atexit.register(close_db_pool)

    return app 