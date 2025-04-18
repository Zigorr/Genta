# agency.py (main script)
import os
import sys
import json
import gradio as gr
from agency_swarm import Agency
from agency_swarm import set_openai_key
from dotenv import load_dotenv

# --- Flask Imports ---
from flask import Flask, request, render_template_string, redirect, url_for, flash, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.dispatcher import DispatcherMiddleware # Import Dispatcher
from a2wsgi import WSGIMiddleware # Import WSGI Middleware

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

# --- Flask App Setup (For Auth Routes Only) ---
flask_app = Flask(__name__) # Rename to avoid conflict
flask_app.secret_key = FLASK_SECRET_KEY # Needed for sessions
login_manager = LoginManager()
login_manager.init_app(flask_app)
# login_manager.login_view = 'login' # We handle redirects manually now or via dispatcher

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

# --- Authentication Routes (Defined on flask_app) ---
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
  <p>Don't have an account? <a href="/register">Register here</a></p> <!-- Hardcoded paths for simplicity -->
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
   <p>Already have an account? <a href="/login">Login here</a></p> <!-- Hardcoded paths -->
</body>
</html>
'''

# Add the root route back to Flask app
@flask_app.route('/')
@login_required
def index():
    # If user is logged in (@login_required passed), redirect to the Gradio app
    return redirect('/gradio') # Use the mount path for Gradio

@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/gradio') # Redirect to gradio mount point
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_db.get(username)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(id=username, password_hash=user_data['password_hash'])
            login_user(user)
            flash('Logged in successfully.')
            # Ensure redirect goes to the correct Gradio path after login
            return redirect('/gradio')
        else:
            flash('Invalid username or password')
    return render_template_string(LOGIN_TEMPLATE)

@flask_app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/gradio') # Redirect to gradio mount point
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
            return redirect('/login') # Redirect to login page
    return render_template_string(REGISTER_TEMPLATE)

@flask_app.route('/logout')
@login_required # This still works as it's part of the Flask app context
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect('/login') # Redirect to login page

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

# --- Manual Gradio Interface Setup ---
with gr.Blocks() as manual_gradio_interface:
    gr.Markdown("## Website Monitor Agency Chat")
    chatbot = gr.Chatbot(height=600, type='messages')
    msg = gr.Textbox(label="Your Message", placeholder="Enter task (e.g., monitor URL X with selector Y)")
    clear = gr.Button("Clear Chat")

    def stateless_chat_handler(message, history):
        print(f"User message: {message}")
        try:
            response_text = agency.get_completion(message)
            print(f"Agency response: {response_text}")
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response_text})
            return "", history
        except Exception as e:
            print(f"Error during agency completion: {e}")
            import traceback
            tb_str = traceback.format_exc()
            error_msg = f"An error occurred: {e}\\nTraceback:\\n{tb_str}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_msg})
            return "", history

    msg.submit(stateless_chat_handler, [msg, chatbot], [msg, chatbot])
    clear.click(lambda: (None, []), None, [msg, chatbot], queue=False)

# --- Create WSGI Apps ---
# Get the underlying ASGI app from Gradio Blocks
gradio_asgi_app = gr.routes.App.create_app(manual_gradio_interface)
# Wrap the ASGI app with WSGIMiddleware
gradio_wsgi_app = WSGIMiddleware(gradio_asgi_app)

# --- Create Authentication Middleware for Gradio WSGI App ---
# This middleware checks if the user is logged in *before* passing to Gradio
class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Use Flask's session handling within the WSGI environment
        # This requires the request context to be available, which might be tricky
        # A simpler check might be needed, or handle auth differently.
        # Let's try a simple check - this needs flask app context!
        with flask_app.request_context(environ):
            if not current_user.is_authenticated:
                # Redirect to login page - build URL carefully
                login_url = '/login'
                start_response('302 Found', [('Location', login_url)])
                return []
        # If authenticated, proceed to the Gradio app
        return self.app(environ, start_response)

# Apply the auth middleware *only* to the Gradio app
protected_gradio_wsgi_app = AuthMiddleware(gradio_wsgi_app)

# --- Create Main Application with Dispatcher ---
# Dispatcher sends requests based on path prefix
# '/' goes to the Flask app (for auth routes)
# '/gradio' goes to the protected Gradio app
application = DispatcherMiddleware(flask_app, {
    '/gradio': protected_gradio_wsgi_app
})

# --- Main Entry Point (for Local Development ONLY) ---
if __name__ == "__main__":
    # Run the main 'application' dispatcher using Werkzeug's development server
    from werkzeug.serving import run_simple
    print("--- Starting Werkzeug Development Server with Dispatcher ---")
    print("--- THIS IS FOR DEVELOPMENT ONLY - Use gunicorn in production ---")
    # Access via http://127.0.0.1:5000/login or http://127.0.0.1:5000/register
    # Login will redirect to http://127.0.0.1:5000/gradio
    run_simple('0.0.0.0', 5000, application, use_debugger=True, use_reloader=True) 