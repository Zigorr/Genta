# agency.py (main script)
import os
import sys
import json
import gradio as gr
from agency_swarm import Agency
from agency_swarm import set_openai_key
from dotenv import load_dotenv

# --- Flask Imports ---
from flask import Flask, request, render_template_string, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import agents using SMM pattern
from MonitorCEO.MonitorCEO import MonitorCEO
from WebsiteMonitor.WebsiteMonitor import WebsiteMonitor

# --- Configuration & Constants ---
load_dotenv(override=True)
DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "a-secure-default-secret-key-for-dev-change-me") # CHANGE FOR PRODUCTION!

# --- Ensure data directory exists ---
os.makedirs(DATA_DIR, exist_ok=True)

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

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY # Needed for sessions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect to 'login' view if user is not logged in

# --- User Management ---
class User(UserMixin):
    def __init__(self, id, password_hash):
        self.id = id
        self.password_hash = password_hash

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

users_db = load_users() # Load users into memory (simple approach)

@login_manager.user_loader
def load_user(user_id):
    user_data = users_db.get(user_id)
    if user_data:
        return User(id=user_id, password_hash=user_data['password_hash'])
    return None

# --- Authentication Routes ---
LOGIN_TEMPLATE = '''
<!doctype html>
<html>
<head><title>Login</title></head>
<body>
  <h1>Login</h1>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <ul>{% for message in messages %}<li>{{ message }}</li>{% endfor %}</ul>
    {% endif %}
  {% endwith %}
  <form method="post">
    Username: <input type="text" name="username"><br>
    Password: <input type="password" name="password"><br>
    <input type="submit" value="Login">
  </form>
  <p>Don't have an account? <a href="{{ url_for('register') }}">Register here</a></p>
</body>
</html>
'''

REGISTER_TEMPLATE = '''
<!doctype html>
<html>
<head><title>Register</title></head>
<body>
  <h1>Register</h1>
   {% with messages = get_flashed_messages() %}
    {% if messages %}
      <ul>{% for message in messages %}<li>{{ message }}</li>{% endfor %}</ul>
    {% endif %}
  {% endwith %}
  <form method="post">
    Username: <input type="text" name="username"><br>
    Password: <input type="password" name="password"><br>
    <input type="submit" value="Register">
  </form>
   <p>Already have an account? <a href="{{ url_for('login') }}">Login here</a></p>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('gradio_app'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_db.get(username)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(id=username, password_hash=user_data['password_hash'])
            login_user(user)
            flash('Logged in successfully.')
            return redirect(url_for('gradio_app')) # Redirect to the Gradio app route
        else:
            flash('Invalid username or password')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('gradio_app'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users_db:
            flash('Username already exists')
        elif not username or not password:
             flash('Username and password cannot be empty')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            users_db[username] = {'password_hash': hashed_password}
            save_users(users_db) # Persist user
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
    return render_template_string(REGISTER_TEMPLATE)

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

# --- Gradio Interface Setup ---
# Use launch=False to get the Gradio app object without starting a server
# We'll let Flask manage the server
gradio_interface = agency.demo_gradio(launch=False)

# --- Mount Gradio App on Flask ---
@app.route('/')
@login_required # Protect the Gradio interface
def gradio_app():
    # This function now needs to return the HTML/response for the Gradio app.
    # Mounting handles this, but we need a simple view function.
    # We will use gr.mount_gradio_app below which is the preferred way.
    # This route definition is mainly for Flask-Login to know it's a protected endpoint.
    # A better approach might be needed if Flask doesn't automatically serve the mount point.
    # Let's return a simple placeholder, mounting handles the real work.
    return "Loading Monitoring Agency..."

app = gr.mount_gradio_app(app, gradio_interface, path="/")

# --- Main Entry Point (for Gunicorn/Waitress) ---
# The Flask 'app' object is the entry point for WSGI servers
# We don't need the __main__ block to call demo_gradio or app.run() anymore

if __name__ == "__main__":
    # For local development ONLY, use Flask's built-in server:
    print("--- Starting Flask Development Server ---")
    print("--- THIS IS FOR DEVELOPMENT ONLY - Use gunicorn/waitress in production ---")
    # Note: This won't use the PORT env var like gunicorn, runs on default 5000
    # Access via http://127.0.0.1:5000
    app.run(debug=True, host='0.0.0.0', port=5000) 