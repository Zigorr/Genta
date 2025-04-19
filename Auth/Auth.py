# Auth/Auth.py

import os
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

# Import database functions and User model from the Database module
# Assumes Database module is at the same level as Auth
# Import directly from database_manager again
from Database.database_manager import (
    User, get_user_by_id, get_user_by_username, add_user, get_user_by_google_id
)

# Define the Blueprint for authentication routes
# Renamed to _auth_bp internally, expose via factory
_auth_bp = Blueprint('auth', __name__, template_folder='templates')

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
        # REMOVED client_id=current_app.config.get("GOOGLE_OAUTH_CLIENT_ID"),
        # REMOVED client_secret=current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
        redirect_to="auth.google_logged_in_handler", # Use blueprint name
        login_url="/google", # Relative to blueprint prefix
        authorized_url="/google/authorized" # Relative to blueprint prefix
    )
    # Register Google blueprint *within* the auth blueprint
    _auth_bp.register_blueprint(google_bp, url_prefix="/login", name="google") # Give nested blueprint a name

    return _auth_bp

# --- Authentication Routes (Defined within the Blueprint) ---

@_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index')) # Redirect to main index
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Use index 3 for google_id after DB change
        db_user = get_user_by_username(username)
        # Check password only if user exists and password_hash is not null
        if db_user and db_user[2] and check_password_hash(db_user[2], password):
            # Use correct indices based on get_user_by_username returning (id, username, password_hash, google_id)
            user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2])
            login_user(user)
            flash('Logged in successfully.')
            next_page = session.pop('_flashed_next_url', None) or url_for('index') # Main index
            return redirect(next_page)
        else:
            flash('Invalid username or password')
    # Pass the template path relative to the app's template folder or configure blueprint template folder
    return render_template('login.html')

@_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index')) # Main index
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        # Add regex import if needed here or at top level
        import re
        error = None
        if len(password) < 8:
            error = 'Password must be at least 8 characters long.'
        elif not re.search(r"[A-Z]", password): # Ensure regex is available
            error = 'Password must contain at least one uppercase letter.'
        # ... (rest of password validation) ...

        if error:
            flash(error)
        elif get_user_by_username(username):
            flash('Username already exists')
        elif not username or not password:
             flash('Username and password cannot be empty')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            success, _ = add_user(username, hashed_password) # Ignore returned ID here
            if success:
                flash('Registration successful! Please login.')
                return redirect(url_for('auth.login')) # Redirect to blueprint login
            else:
                flash('An error occurred during registration. Please try again.')

    return render_template('register.html')


@_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login')) # Redirect to blueprint login


# --- Google OAuth Handlers (within the Blueprint) ---

# Note: 'redirect_to' in make_google_blueprint points here now
@_auth_bp.route("/google_logged_in") # No prefix needed, handled by blueprint
@oauth_authorized.connect_via("google") # Connect via name given to nested blueprint
def google_logged_in_handler(blueprint, token):
    if not token:
        flash("Failed to log in with Google.", category="error")
        return redirect(url_for(".login")) # Use relative .login

    resp = blueprint.session.get("/oauth2/v3/userinfo")
    if not resp.ok:
        msg = "Failed to fetch user info from Google."
        flash(msg, category="error")
        print(f"Error fetching user info: {resp.status_code} - {resp.text}")
        return redirect(url_for(".login"))

    google_info = resp.json()
    google_user_id = str(google_info["sub"])
    email = google_info.get("email")

    if not email:
        flash("Google account does not have an email associated.", category="error")
        return redirect(url_for(".login"))

    user_data = get_user_by_google_id(google_user_id)
    user = None
    if user_data:
        # Use correct indices based on get_user_by_google_id returning (id, username, password_hash)
        user = User(id=user_data[0], username=user_data[1], password_hash=user_data[2])
        print(f"Found existing user by Google ID: {user.id}")
    else:
        existing_user_by_email = get_user_by_username(email)
        # Correct index for google_id is 3
        if existing_user_by_email and existing_user_by_email[3] is None:
             flash("An account with this email already exists, but is not linked to a Google account. Please login using your password or register differently.", category="warning")
             return redirect(url_for(".login"))
        # Correct index for google_id is 3
        elif existing_user_by_email and existing_user_by_email[3] == google_user_id:
             # Use correct indices based on get_user_by_username returning (id, username, password_hash, google_id)
             user = User(id=existing_user_by_email[0], username=existing_user_by_email[1], password_hash=existing_user_by_email[2])
             print(f"Found existing user by email matching Google ID: {user.id}")
        else:
            print(f"Creating new user for Google ID {google_user_id} with email {email}")
            success, new_user_id = add_user(username=email, google_id=google_user_id)
            if success:
                user = User(id=new_user_id, username=email, password_hash=None)
                print(f"New user created with ID: {new_user_id}")
            else:
                flash("Failed to create a new user account from Google profile.", category="error")
                return redirect(url_for(".login"))

    if user:
        login_user(user)
        flash("Successfully logged in with Google.")
        next_url = session.pop('_flashed_next_url', None) or url_for('index') # Main index
        return redirect(next_url)
    else:
        flash("Could not log you in with Google.", category="error")
        return redirect(url_for(".login"))


@oauth_error.connect_via("google") # Connect via name given to nested blueprint
def google_oauth_error(blueprint, error, error_description=None, error_uri=None):
    msg = (
        "OAuth error from {name}! "
        "error={error} description={description} uri={uri}"
    ).format(
        name=blueprint.name, error=error, description=error_description, uri=error_uri,
    )
    print(f"OAuth Error: {msg}")
    flash(msg, category="error")
    return redirect(url_for(".login")) 