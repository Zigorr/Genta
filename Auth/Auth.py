# Auth/Auth.py

import os
import re # Moved import re to top level
import traceback # Added import for exception logging
from flask import (
    Blueprint, request, render_template, redirect, url_for, flash, session,
    current_app # Import current_app to access config
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized, oauth_error
import sys

# Import database functions and User model from the Database module
# Assumes Database module is at the same level as Auth
# Import directly from database_manager again
from Database.database_manager import (
    User, get_user_by_id, get_user_by_username, add_user, get_user_by_google_id
)

# Import Forms - Assuming they are in Auth/forms.py
try:
    from .forms import LoginForm, RegistrationForm
except ImportError:
    # Handle case where forms.py might not exist or has different naming
    # Provide default empty forms to prevent crashes, but log a warning.
    # Ideally, create forms.py if it's missing.
    print("WARNING: Could not import LoginForm or RegistrationForm from Auth.forms. Check if forms.py exists and defines these classes.", file=sys.stderr)
    from wtforms import Form
    class LoginForm(Form): pass
    class RegistrationForm(Form): pass


# Define the Blueprint for authentication routes
# Renamed to _auth_bp internally, expose via factory
# Remove template_folder to use the main app\'s template folder
_auth_bp = Blueprint('auth', __name__)

# We need access to the login_manager created in the main app
# We'll configure it within the factory function or pass it in
login_manager_instance = None

def create_auth_blueprint(login_manager):
    """Factory function to create and configure the auth blueprint."""
    global login_manager_instance
    login_manager_instance = login_manager
    login_manager.login_view = 'auth.login' # Use blueprint name for view

    # User loader needs to be associated with the main app's login_manager
    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            print(f"Warning: Invalid user_id format '{user_id}' received from session cookie. Treating as logged out.")
            return None
        db_user = get_user_by_id(user_id_int)
        if db_user:
            # Use correct indices based on get_user_by_id returning (id, username, password_hash)
            return User(id=db_user[0], username=db_user[1], password_hash=db_user[2])
        return None

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.endpoint != 'auth.login':
            session['_flashed_next_url'] = request.url
        flash("You must be logged in to view this page.")
        return redirect(url_for('auth.login')) # Redirect to blueprint login view

    # --- Google OAuth Setup within Auth ---
    # Create Google OAuth blueprint (specific to this auth module)
    # Flask-Dance will automatically pick up client_id/secret from app.config later
    google_bp = make_google_blueprint(
        scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
        redirect_to="auth.google_callback", # Use endpoint name string again
        login_url="/google",
        authorized_url="/google/authorized"
    )
    # Register Google blueprint *within* the auth blueprint
    _auth_bp.register_blueprint(google_bp, url_prefix="/login", name="google") # Give nested blueprint a name

    return _auth_bp

# --- Intermediate Google Routes to Set Intent ---

@_auth_bp.route('/google/start_login')
def google_start_login():
    session['google_action'] = 'login'
    # Redirect to the actual Flask-Dance Google endpoint
    # The endpoint name is 'google.login' relative to the main auth blueprint
    return redirect(url_for("google.login")) 

@_auth_bp.route('/google/start_register')
def google_start_register():
    session['google_action'] = 'register'
    # Redirect to the actual Flask-Dance Google endpoint
    return redirect(url_for("google.login"))

# --- Authentication Routes (Defined within the Blueprint) ---

@_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index')) # Redirect to main index

    form = LoginForm() # Instantiate the form

    if form.validate_on_submit(): # Use form validation
        username = form.username.data # Access data via form
        password = form.password.data # Access data via form
        remember_me = form.remember_me.data

        db_user = get_user_by_username(username)
        # Check password only if user exists and password_hash is not null
        if db_user and db_user[2] and check_password_hash(db_user[2], password):
            user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2])
            login_user(user, remember=remember_me) # Pass remember_me flag
            flash('Logged in successfully.', category='success')
            next_page = session.pop('_flashed_next_url', None) or url_for('index') # Main index
            return redirect(next_page)
        else:
            flash('Invalid username or password', category='error')

    # Pass the form object to the template for both GET and failed POST
    return render_template('login.html', title='Login', form=form)

@_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index')) # Main index

    form = RegistrationForm() # Instantiate the form

    if form.validate_on_submit(): # Use form validation
        username = form.username.data.strip() # Access data via form
        password = form.password.data # Access data via form

        # Password complexity checks can be moved to the form validator if desired
        error = None
        # Check length
        if len(password) < 8:
            error = 'Password must be at least 8 characters long.'
        # Check for uppercase letter
        elif not re.search(r"[A-Z]", password):
            error = 'Password must contain at least one uppercase letter.'
        # Check for numeral
        elif not re.search(r"[0-9]", password): # Or use \\d
            error = 'Password must contain at least one numeral.'
        # Check if username exists (also could be a form validator)
        elif get_user_by_username(username):
             error = 'Username already exists'

        if error:
            flash(error, category='error')
        # No need to check for empty username/password here, form validators handle it
        # elif not username or not password:
        #      flash(\'Username and password cannot be empty\')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            success, _ = add_user(username, hashed_password) # Ignore returned ID here
            if success:
                flash('Registration successful! Please login.', category='success')
                return redirect(url_for('auth.login')) # Redirect to blueprint login
            else:
                flash('An error occurred during registration. Please try again.', category='error')

    # Pass the form object to the template for both GET and failed POST
    return render_template('register.html', title='Register', form=form)


@_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login')) # Redirect to blueprint login


# --- Google OAuth Handlers (within the Blueprint) ---

# Helper function to process the user data after callback
def _process_google_login(google_info):
    """Processes user info obtained from Google, finds/creates user, returns redirect."""
    google_user_id = str(google_info["sub"])
    email = google_info.get("email")
    action = session.pop('google_action', 'login') # Get and remove action, default to login

    if not email:
        flash("Google account does not have an email associated.", category="error")
        return redirect(url_for(".login"))

    # 1. Check if user exists by Google ID
    user_data = get_user_by_google_id(google_user_id)
    user = None
    login_message = ""
    login_category = "success"

    if user_data:
        # Case 1: Google account already linked
        user = User(id=user_data[0], username=user_data[1], password_hash=user_data[2])
        print(f"Found existing user by Google ID: {user.id}")
        
        # *** Check intent if user exists ***
        if action == 'register':
            flash("You already have an account linked with Google. Please sign in.", category="info")
            return redirect(url_for(".login"))
        else:
            login_message = "Welcome back! Logged in with Google."

    else:
        # 2. Check if user exists by email (but not linked to this Google ID)
        existing_user_by_email = get_user_by_username(email)
        if existing_user_by_email:
            # Check if the existing email account has NO google ID linked
            if existing_user_by_email[3] is None:
                 # Case 2: Manual account with this email exists
                flash("An account already exists with this email, but it's not linked to Google. Please log in with your password.", category="warning")
                return redirect(url_for(".login"))
            # Edge case: email matches but google ID doesn't? Should be rare.
            else:
                flash("Account email matches, but Google ID does not. Please contact support or log in manually.", category="error")
                return redirect(url_for(".login"))
        else:
            # 3. Create new user if neither Google ID nor email exists
            print(f"Creating new user for Google ID {google_user_id} with email {email}")
            success, new_user_id = add_user(username=email, google_id=google_user_id)
            if success:
                user = User(id=new_user_id, username=email, password_hash=None)
                print(f"New user created with ID: {new_user_id}")
                login_message = "Account created and logged in with Google."
            else:
                flash("Failed to create a new user account from Google profile.", category="error")
                return redirect(url_for(".login"))

    # Log in user and redirect (if user object was created/found and not redirected earlier)
    if user:
        login_user(user) # Consider adding remember=True if desired
        if login_message: # Only flash if we didn't redirect earlier
             flash(login_message, category=login_category)
        next_url = session.pop('_flashed_next_url', None) or url_for('index')
        return redirect(next_url)
    else:
        # Fallback if user creation failed or another logic path was missed
        flash("Could not log you in with Google.", category="error")
        return redirect(url_for(".login"))

# NEW: Explicit callback route
@_auth_bp.route("/google/callback")
def google_callback():
    print("DEBUG: Entered /google/callback route")
    try:
        # Check if authorized and retrieve token from session proxy
        if not google.authorized:
            flash("Authorization with Google failed or was denied.", category="error")
            print("ERROR: google.authorized is False in callback.")
            return redirect(url_for('.login'))

        token = google.token # Access the token directly
        if not token:
            # This case might be redundant if google.authorized is False, but check defensively
            flash("Failed to retrieve Google token after authorization.", category="error")
            print("ERROR: google.token is None/empty after authorization.")
            return redirect(url_for('.login'))

        print(f"DEBUG: Retrieved token: {token}")

        # Fetch user info using the token (google object acts as the session)
        resp = google.get("/oauth2/v3/userinfo")
        if not resp.ok:
            msg = "Failed to fetch user info from Google."
            flash(msg, category="error")
            print(f"Error fetching user info: {resp.status_code} - {resp.text}")
            return redirect(url_for(".login"))
        
        google_info = resp.json()
        print(f"DEBUG: Received google_info: {google_info}")

        # Process login/registration using the helper function
        return _process_google_login(google_info)

    except Exception as e:
        # Use the imported traceback module correctly
        print(f"ERROR in google_callback: {e}", file=sys.stderr) # Need import sys
        traceback.print_exc()
        flash("An error occurred during Google login. Please try again.", category="error")
        return redirect(url_for(".login"))

# --- Authentication Routes (Defined within the Blueprint) ---
# ... (login, register, logout routes)


# REMOVED Signal Handlers
# @oauth_authorized.connect_via("google") ...
# @oauth_error.connect_via("google") ... 