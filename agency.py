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

# --- Flask App Setup (Main App) ---
app = Flask(__name__) # Use standard 'app' name
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

users_db = load_users()

@login_manager.user_loader
def load_user(user_id):
    user_data = users_db.get(user_id)
    if user_data:
        return User(id=user_id, password_hash=user_data['password_hash'])
    return None

# --- Authentication Routes (Defined on app) ---
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

# Root redirects to Gradio if logged in, else to login
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('gradio_app_mount')) # Redirect to the Gradio mount point
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('gradio_app_mount'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_db.get(username)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(id=username, password_hash=user_data['password_hash'])
            login_user(user)
            flash('Logged in successfully.')
            next_page = request.args.get('next')
            # IMPORTANT: Ensure next_page is safe before redirecting
            # For simplicity, redirect only to gradio mount point
            return redirect(url_for('gradio_app_mount'))
        else:
            flash('Invalid username or password')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('gradio_app_mount'))
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
            save_users(users_db)
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
            error_msg = f"An error occurred: {e}\nTraceback:\n{tb_str}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_msg})
            return "", history

    msg.submit(stateless_chat_handler, [msg, chatbot], [msg, chatbot])
    clear.click(lambda: (None, []), None, [msg, chatbot], queue=False)

# --- Protect Gradio Mount using before_request --- 
GRADIO_PATH = "/gradio" # Define path constant

@app.before_request
def protect_gradio_mount():
    # Check if the request path starts with the Gradio mount path
    if request.path.startswith(GRADIO_PATH):
        # If it's for Gradio and user is not authenticated, redirect to login
        if not current_user.is_authenticated:
            # Pass the original path as 'next' for redirect after login
            return redirect(url_for('login', next=request.path))
    # If path is not Gradio or user is authenticated, continue as normal
    pass

# --- Mount Gradio App on Flask --- 
# Use a dummy endpoint name for url_for in redirects
app = gr.mount_gradio_app(app, manual_gradio_interface, path=GRADIO_PATH, _api_mode=True, endpoint_name_for_url_for="gradio_app_mount")

# --- Main Entry Point (for Gunicorn/Waitress - runs 'app') ---
if __name__ == "__main__":
    # Run the Flask 'app' directly for local development
    print("--- Starting Flask Development Server ---")
    print("--- THIS IS FOR DEVELOPMENT ONLY - Use gunicorn/waitress in production ---")
    app.run(debug=True, host='0.0.0.0', port=5000) 