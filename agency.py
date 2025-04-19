# agency.py (main script)
import os
import sys
import json
import re
# Removed psycopg2 imports, handled in database_manager
# import psycopg2 # Import PostgreSQL adapter
# from psycopg2 import pool # Import connection pool
# import gradio as gr # Removed Gradio UI import
from agency_swarm import Agency
from agency_swarm import set_openai_key
from dotenv import load_dotenv

# --- Flask Imports ---
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, g # Added g for db connection storage
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix # Import ProxyFix
# Removed a2wsgi import

# Flask-Dance imports
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized, oauth_error
from flask import session # Import Flask session

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import agents using SMM pattern
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# Import database functions
from Database.database_manager import init_db, close_db_pool, User, get_user_by_id, get_user_by_username, add_user
from Database.database_manager import get_user_by_google_id

# --- Configuration & Constants ---
load_dotenv(override=True)
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "a-secure-default-secret-key-for-dev-change-me") # CHANGE FOR PRODUCTION!
# DATABASE_URL is now loaded within database_manager
# DATABASE_URL = os.getenv("DATABASE_URL") # Get Database URL from environment

# --- Database Setup --- (Moved to database_manager.py)
# # Simple connection pool
# db_pool = None
#
# def get_db_connection():
#     global db_pool
#     if db_pool is None:
#         if not DATABASE_URL:
#             print("Error: DATABASE_URL environment variable not set.")
#             sys.exit("Database configuration error.")
#         try:
#             print("Initializing database connection pool...")
#             db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
#             print("Database connection pool initialized.")
#         except (Exception, psycopg2.DatabaseError) as error:
#             print(f"Error while initializing database pool: {error}")
#             sys.exit("Database connection error.")
#
#     # Get a connection from the pool
#     conn = db_pool.getconn()
#     if not conn:
#         print("Error: Failed to get connection from pool.")
#         sys.exit("Database connection error.")
#     return conn
#
# def return_db_connection(conn):
#     if db_pool and conn:
#         db_pool.putconn(conn)
#
# def init_db():
#     conn = None
#     cur = None
#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()
#         print("Creating users table if it doesn't exist...")
#         cur.execute("""
#             CREATE TABLE IF NOT EXISTS users (
#                 id SERIAL PRIMARY KEY,
#                 username VARCHAR(80) UNIQUE NOT NULL,
#                 password_hash VARCHAR(255) NOT NULL
#             );
#         """)
#         conn.commit()
#         print("Users table checked/created.")
#     except (Exception, psycopg2.DatabaseError) as error:
#         print(f"Error while initializing database: {error}")
#         # Don't exit here, maybe the app can run partially or retry?
#     finally:
#         if cur: cur.close()
#         if conn: return_db_connection(conn)

# --- LLM Configuration Check ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY environment variable not found.")
    print("Please ensure it is set in your deployment environment (e.g., Railway Variables) or local .env file.")
    sys.exit(1)
else:
    try:
        set_openai_key(api_key)
        print("OpenAI API Key loaded and set successfully.")
    except Exception as e:
        print(f"Error setting OpenAI API key: {e}")
        sys.exit(1)

# --- Flask App Setup (Main App) ---
app = Flask(__name__) # Use standard 'app' name

# Apply ProxyFix to handle X-Forwarded-Proto (for HTTPS detection behind proxy)
# trust 1 level of proxy (Railway's load balancer)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = FLASK_SECRET_KEY

# Configure session timeout (5 minutes of inactivity)
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_REFRESH_EACH_REQUEST'] = True # Default, but explicit is good

# OAuth Configuration
app.config["GOOGLE_OAUTH_CLIENT_ID"] = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
# For local testing over http:
if os.getenv("OAUTHLIB_INSECURE_TRANSPORT") == "1":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("WARNING: OAUTHLIB_INSECURE_TRANSPORT enabled for local HTTP testing.")

# Create Google OAuth blueprint
google_bp = make_google_blueprint(
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to="google_logged_in_handler", # Redirect to a custom handler after auth
    login_url="/login/google", # Use absolute path
    authorized_url="/login/google/authorized" # Use absolute path
)
# app.register_blueprint(google_bp, url_prefix="/login") # REMOVED url_prefix
app.register_blueprint(google_bp) # Register at root

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize DB on startup (uses imported init_db)
with app.app_context():
    init_db()

# Add shutdown hook to close DB pool
import atexit
atexit.register(close_db_pool)

# --- User Management (Database Version) --- (User class moved, functions imported)
# class User(UserMixin):
#     def __init__(self, id, username, password_hash):
#         self.id = id # Use database ID
#         self.username = username
#         self.password_hash = password_hash
#
# # Replaces old load_users/save_users
# def get_user_by_id(user_id):
#     conn = None
#     cur = None
#     user_data = None
#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()
#         cur.execute("SELECT id, username, password_hash FROM users WHERE id = %s", (user_id,))
#         user_data = cur.fetchone()
#     except (Exception, psycopg2.DatabaseError) as error:
#         print(f"Error fetching user by ID: {error}")
#     finally:
#         if cur: cur.close()
#         if conn: return_db_connection(conn)
#     return user_data
#
# def get_user_by_username(username):
#     conn = None
#     cur = None
#     user_data = None
#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()
#         cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
#         user_data = cur.fetchone()
#     except (Exception, psycopg2.DatabaseError) as error:
#         print(f"Error fetching user by username: {error}")
#     finally:
#         if cur: cur.close()
#         if conn: return_db_connection(conn)
#     return user_data
#
# def add_user(username, password_hash):
#     conn = None
#     cur = None
#     success = False
#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()
#         cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
#         conn.commit()
#         success = True
#     except (Exception, psycopg2.DatabaseError) as error:
#         print(f"Error adding user: {error}")
#         if conn: conn.rollback() # Rollback on error
#     finally:
#         if cur: cur.close()
#         if conn: return_db_connection(conn)
#     return success

@login_manager.user_loader
def load_user(user_id):
    # Automatically handle potentially invalid user_id format from cookie
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        # If user_id is not a valid integer (e.g., old cookie with username)
        print(f"Warning: Invalid user_id format '{user_id}' received from session cookie. Treating as logged out.")
        return None

    # Proceed only if user_id was a valid integer
    db_user = get_user_by_id(user_id_int) # Uses imported function with integer ID
    if db_user:
        # Create User object (imported from database_manager)
        # Unpack the tuple: id=db_user[0], username=db_user[1], password_hash=db_user[2]
        return User(id=db_user[0], username=db_user[1], password_hash=db_user[2])
    return None

# --- Authentication Routes (Using Database) ---

@app.route('/')
@login_required
def index():
    # Render the chat interface template
    return render_template('chat.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db_user = get_user_by_username(username) # Uses imported function
        # Check if user exists and password matches hash from DB
        # db_user tuple: (id, username, password_hash)
        if db_user and check_password_hash(db_user[2], password):
            user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2]) # Uses imported User class
            login_user(user)
            flash('Logged in successfully.')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password')
    # Render login form from template file
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        # --- Password Validation --- 
        error = None
        if len(password) < 8:
            error = 'Password must be at least 8 characters long.'
        elif not re.search(r"[A-Z]", password):
            error = 'Password must contain at least one uppercase letter.'
        # Optional: Add more checks (lowercase, number, symbol) here if desired
        # elif not re.search(r"[a-z]", password):
        #     error = 'Password must contain at least one lowercase letter.'
        # elif not re.search(r"[0-9]", password):
        #     error = 'Password must contain at least one number.'
        
        if error:
            flash(error)
        # --- End Password Validation ---
        
        # --- Check if username exists in DB ---
        elif get_user_by_username(username): # Uses imported function
            flash('Username already exists')
        elif not username or not password:
             flash('Username and password cannot be empty')
        else:
            # Hash password and add user to DB
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            if add_user(username, hashed_password): # Uses imported function
                flash('Registration successful! Please login.')
                return redirect(url_for('login'))
            else:
                flash('An error occurred during registration. Please try again.')
                
    # Render register form
    return render_template('register.html') # Assumes templates/register.html exists

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

# --- Instantiate Agents ---
print("Initializing agents...")
try:
    monitor_ceo = MonitorCEO()
    monitor_worker = WebsiteMonitor()
    print("Agents initialized successfully.")
except Exception as e:
    print(f"Error initializing agents: {e}")
    sys.exit(1)

# --- Define Agency ---
print("Creating agency structure...")
agency = Agency(
    agency_chart=[
        monitor_ceo,
        [monitor_ceo, monitor_worker],
    ],
    shared_instructions='agency_manifesto.md',
)
print("Agency structure created successfully.")

# --- API Endpoint for Chat ---
@app.route('/api/chat', methods=['POST'])
@login_required # Protect the API endpoint
def chat_api():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    message = data.get('message')

    if not message:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    print(f"API received message from {current_user.id}: {message}")
    try:
        # Get completion from the agency
        response_text = agency.get_completion(message)
        print(f"API sending response: {response_text}")
        return jsonify({"response": response_text})

    except Exception as e:
        print(f"Error during agency completion via API: {e}")
        import traceback
        traceback.print_exc() # Log full traceback to server logs
        return jsonify({"error": f"An internal error occurred: {e}"}), 500

# --- Remove Gradio Specific Code ---
# with gr.Blocks() as manual_gradio_interface:
#     ...
# app = gr.mount_gradio_app(...)
# @app.before_request
# def protect_gradio_mount():
#     ...

# --- Google OAuth Login Handler ---
# This function runs after Google successfully authenticates the user
@app.route("/google_logged_in") # Route referred to in redirect_to for blueprint
@oauth_authorized.connect_via(google_bp)
def google_logged_in_handler(blueprint, token):
    if not token:
        flash("Failed to log in with Google.", category="error")
        return redirect(url_for("login"))

    # Get user info from Google
    resp = blueprint.session.get("/oauth2/v3/userinfo")
    if not resp.ok:
        msg = "Failed to fetch user info from Google."
        flash(msg, category="error")
        print(f"Error fetching user info: {resp.status_code} - {resp.text}")
        return redirect(url_for("login"))

    google_info = resp.json()
    google_user_id = str(google_info["sub"]) # Unique Google ID
    email = google_info.get("email")

    if not email:
        flash("Google account does not have an email associated. Cannot log in.", category="error")
        return redirect(url_for("login"))

    # Find this user in the database by Google ID
    user_data = get_user_by_google_id(google_user_id)

    user = None
    if user_data:
        # User found by Google ID - log them in
        user = User(id=user_data[0], username=user_data[1], password_hash=user_data[2])
        print(f"Found existing user by Google ID: {user.id}")
    else:
        # User not found by Google ID, check if email exists (optional - careful)
        # For simplicity, we'll create a new user if Google ID is not found
        # We use email as the username for OAuth users
        existing_user_by_email = get_user_by_username(email)
        # Check if email exists AND google_id is NULL (index 3 is now google_id)
        if existing_user_by_email and existing_user_by_email[3] is None: 
            # Optional: Link existing account? Requires careful handling.
            # For now, let's prevent login if email exists but google_id is not set
            flash("An account with this email already exists, but is not linked to a Google account. Please login using your password or register differently.", category="warning")
            return redirect(url_for("login"))
        # Check if email exists AND google_id matches the one from Google
        elif existing_user_by_email and existing_user_by_email[3] == google_user_id:
             # This case handles if get_user_by_google_id somehow failed but email lookup works
             user = User(id=existing_user_by_email[0], username=existing_user_by_email[1], password_hash=existing_user_by_email[2])
             print(f"Found existing user by email matching Google ID: {user.id}")
        else:
            # Create a new user associated with this Google account
            # Use email as username, no password hash needed for OAuth users
            print(f"Creating new user for Google ID {google_user_id} with email {email}")
            success, new_user_id = add_user(username=email, google_id=google_user_id)
            if success:
                user = User(id=new_user_id, username=email, password_hash=None) # Create User object for login
                print(f"New user created with ID: {new_user_id}")
            else:
                flash("Failed to create a new user account from Google profile.", category="error")
                return redirect(url_for("login"))

    # Log in the user using Flask-Login
    if user:
        login_user(user)
        flash("Successfully logged in with Google.")
        # Redirect to the main page or wherever appropriate after login
        # Check if there was a page user was trying to access
        next_url = session.pop('_flashed_next_url', None) or url_for('index')
        return redirect(next_url)
    else:
        # Should not happen if logic above is correct, but handle defensively
        flash("Could not log you in with Google.", category="error")
        return redirect(url_for("login"))

# Optional: Handle OAuth errors gracefully
@oauth_error.connect_via(google_bp)
def google_oauth_error(blueprint, error, error_description=None, error_uri=None):
    msg = (
        "OAuth error from {name}! "
        "error={error} description={description} uri={uri}"
    ).format(
        name=blueprint.name,
        error=error,
        description=error_description,
        uri=error_uri,
    )
    print(f"OAuth Error: {msg}")
    flash(msg, category="error")
    return redirect(url_for("login"))

@login_manager.unauthorized_handler
def unauthorized():
    # Store the URL they were trying to access if it's not the login page
    if request.endpoint != 'login':
      session['_flashed_next_url'] = request.url
    flash("You must be logged in to view this page.")
    return redirect(url_for('login'))

# --- Main Entry Point (for Gunicorn/Waitress - runs 'app') ---
if __name__ == "__main__":
    # Run the Flask 'app' directly for local development
    print("--- Starting Flask Development Server ---")
    print("--- THIS IS FOR DEVELOPMENT ONLY - Use gunicorn/waitress in production ---")
    app.run(debug=True, host='0.0.0.0', port=5000) 