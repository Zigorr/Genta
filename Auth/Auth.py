# Auth/Auth.py

import os
import re # Moved import re to top level
import traceback # Added import for exception logging
import random # Import random
import string # Import string
from datetime import datetime, timedelta, timezone # Import datetime, timedelta, timezone
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
    User, get_user_by_id, get_user_by_email, add_user, get_user_by_google_id, update_username,
    set_verification_code, get_verification_details, verify_user # Add verification functions
)
from .utils import send_verification_email # Import the email sending function

# Import Forms - Assuming they are in Auth/forms.py
# The try/except is removed as Auth/__init__.py should fix the import path
from .forms import LoginForm, RegistrationForm, VerificationForm # Removed SetUsernameForm if not used
# If SetUsernameForm is still needed, add it back here.

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
        # db_user is (id, username, pwd_hash, google_id, tokens, subscribed, last_reset)
        db_user = get_user_by_id(user_id_int)
        if db_user:
            # Unpack all columns including new ones
            # Indices: 0:id, 1:username, 2:pwd_hash, 3:google_id, 4:tokens, 5:subscribed, 6:last_reset
            #          7:first_name, 8:last_name, 9:email, 10:is_verified
            return User(id=db_user[0], username=db_user[1], password_hash=db_user[2],
                        google_id=db_user[3], tokens_used=db_user[4], is_subscribed=db_user[5],
                        last_token_reset=db_user[6],
                        first_name=db_user[7], last_name=db_user[8], email=db_user[9], is_verified=db_user[10])
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
    # Redirect to the actual Flask-Dance Google endpoint using relative path
    return redirect(url_for(".google.login")) 

@_auth_bp.route('/google/start_register')
def google_start_register():
    session['google_action'] = 'register'
    # Redirect to the actual Flask-Dance Google endpoint using relative path
    return redirect(url_for(".google.login"))

# --- Authentication Routes (Defined within the Blueprint) ---

@_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        password = form.password.data
        remember_me = form.remember_me.data

        db_user = get_user_by_email(email)

        # Step 1: Check if user exists and password is correct
        if db_user and db_user[2] and check_password_hash(db_user[2], password):
            # User exists and password matches
            user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2],
                        google_id=db_user[3], tokens_used=db_user[4], is_subscribed=db_user[5],
                        last_token_reset=db_user[6],
                        first_name=db_user[7], last_name=db_user[8], email=db_user[9], is_verified=db_user[10])

            # Step 2: Check if the account is verified
            if not user.is_verified:
                flash('Your account is not verified. Please check your email for the verification code or register again.', 'warning')
                # Redirect to the verification page, passing the email
                return redirect(url_for('auth.verify_email', email=user.email))

            # Account is verified, proceed with login
            login_user(user, remember=remember_me)
            flash('Logged in successfully.', category='success')
            next_page = session.pop('_flashed_next_url', None) or url_for('index')
            return redirect(next_page)
        else:
            # User not found or password incorrect
            flash('Invalid email or password', category='error')

    return render_template('login.html', title='Login', form=form)

@_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        first_name = form.first_name.data.strip()
        last_name = form.last_name.data.strip()
        email = form.email.data.lower().strip()
        password = form.password.data

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        # Add user, initially NOT verified
        success, new_user_id = add_user(email=email, password_hash=hashed_password,
                                        first_name=first_name, last_name=last_name,
                                        is_verified=False)

        if success and new_user_id:
            try:
                # Generate 4-digit verification code
                verification_code = "".join(random.choices(string.digits, k=4))
                # Set expiration time (e.g., 15 minutes from now)
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
                
                # Store code and expiry in DB
                set_code_success = set_verification_code(new_user_id, verification_code, expires_at)
                
                if set_code_success:
                    # Send verification email
                    send_verification_email(email, verification_code)
                    flash('Registration successful! Please check your email for a 4-digit code to verify your account.', 'info')
                    # Redirect to a new verification page/route
                    return redirect(url_for('auth.verify_email', email=email))
                else:
                    # Handle rare error where code couldn't be saved
                    flash('Registration succeeded, but failed to set verification code. Please contact support.', 'error')
                    # Maybe log this specific error
                    return redirect(url_for('auth.login')) # Or redirect to login anyway?
            except Exception as e:
                 # Handle potential errors during code generation/sending
                 print(f"Error during verification code generation/sending for {email}: {e}")
                 traceback.print_exc()
                 flash('Registration succeeded, but failed to send verification email. Please try logging in or contact support.', 'warning')
                 return redirect(url_for('auth.login')) # Redirect to login
        else:
             flash('Registration failed. The email might already be registered.', category='error')

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
    google_user_id = str(google_info["sub"])
    email = google_info.get("email")
    first_name = google_info.get("given_name", "") # Get first name
    last_name = google_info.get("family_name", "") # Get last name
    # profile_pic = google_info.get("picture") # Optional

    action = session.pop('google_action', 'login')

    if not email:
        flash("Google account does not have an email associated.", category="error")
        return redirect(url_for(".login"))

    user_data = get_user_by_google_id(google_user_id)
    if not user_data:
        # If not found by Google ID, check by email
        user_data = get_user_by_email(email)

    user = None
    login_message = ""
    login_category = "success"

    if user_data:
        # User exists (found by Google ID or Email)
        user_db_id = user_data[0]
        user_db_google_id = user_data[3]
        user_db_email = user_data[9]

        if user_db_google_id == google_user_id:
            # Case 1: Google account already linked - Log them in
            user = User(*user_data) # Unpack all fields
            print(f"Found existing user by Google ID: {user.id}")
            if action == 'register':
                flash("You already have an account linked with this Google profile. Please sign in.", category="info")
                return redirect(url_for(".login"))
            else:
                login_message = "Welcome back! Logged in with Google."
        elif user_db_email == email.lower():
             # Case 2: Account with this email exists, but NOT linked to this Google ID
             # Potential Action: Link the accounts? For now, tell them to log in normally.
            flash("An account exists with this email, but it's linked to a different login method (or no Google account). Please log in with your password or the original Google account.", category="warning")
            return redirect(url_for(".login"))
        else:
             # Should not happen if found by google_id or email, but handle defensively
             flash("An unexpected issue occurred linking your account.", category="error")
             return redirect(url_for(".login"))
    else:
        # Case 3: No existing user found by Google ID or email - Create new user
        print(f"Creating new user record for Google ID {google_user_id} with email {email}")
        # Add user, mark as verified since email comes from Google
        success, new_user_id = add_user(email=email, password_hash=None,
                                        first_name=first_name, last_name=last_name,
                                        google_id=google_user_id, is_verified=True)
        if success:
            # Fetch the newly created user data to log them in
            new_user_data = get_user_by_id(new_user_id)
            if new_user_data:
                user = User(*new_user_data)
                login_message = "Welcome! Your account has been created via Google."
            else:
                flash("Account created, but failed to log you in automatically.", category="warning")
                return redirect(url_for(".login"))
        else:
            flash("Failed to create a new user account from Google profile.", category="error")
            return redirect(url_for(".login"))

    # Log in user if found/created
    if user:
        login_user(user)
        if login_message:
             flash(login_message, category=login_category)
        next_url = session.pop('_flashed_next_url', None) or url_for('index')
        return redirect(next_url)
    else:
        # Fallback error if user object wasn't populated for some reason
        flash("Could not process your Google login.", category="error")
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

# NEW Route for setting username after Google signup
@_auth_bp.route('/set-google-username', methods=['GET', 'POST'])
def set_google_username():
    # Check if a user ID is pending from Google OAuth
    if 'pending_google_user_id' not in session:
        flash('Invalid access to set username page.', 'warning')
        return redirect(url_for('.login'))

    user_id = session['pending_google_user_id']
    form = SetUsernameForm()

    if form.validate_on_submit():
        new_username = form.username.data
        
        # Attempt to update the username for the pending user ID
        # The form validator should have already checked for uniqueness,
        # but update_username also handles potential race conditions.
        success = update_username(user_id, new_username)
        
        if success:
            # Username set successfully, clear the session flag
            session.pop('pending_google_user_id', None)
            
            # Fetch the full user data to log them in
            db_user = get_user_by_id(user_id)
            if db_user:
                user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2],
                            google_id=db_user[3], tokens_used=db_user[4], is_subscribed=db_user[5],
                            last_token_reset=db_user[6])
                login_user(user) # Log the user in
                flash(f'Username set to "{new_username}" and logged in successfully!', 'success')
                return redirect(url_for('index')) # Redirect to main app page
            else:
                # Should not happen, but handle case where user disappeared
                flash('Account setup complete, but failed to log you in automatically. Please try logging in.', 'warning')
                return redirect(url_for('.login'))
        else:
            # update_username returns False if username is taken (or other DB error)
            flash('That username is already taken or an error occurred. Please choose another.', 'error')
            # Fall through to re-render form with errors

    # Render the form on GET request or if POST validation failed
    return render_template('set_username.html', form=form)


# REMOVED Signal Handlers
# @oauth_authorized.connect_via("google") ...
# @oauth_error.connect_via("google") ... 

# --- NEW Verification Route ---
@_auth_bp.route('/verify', methods=['GET', 'POST'])
def verify_email():
    """Handles email verification using a 4-digit code."""
    # Get email from query param (safer than session)
    email = request.args.get('email')
    if not email:
        flash('Email address missing for verification.', 'error')
        return redirect(url_for('auth.login'))

    # Prevent already logged-in and verified users from accessing
    if current_user.is_authenticated and current_user.is_verified:
        return redirect(url_for('index'))

    form = VerificationForm()

    if form.validate_on_submit():
        submitted_code = form.code.data
        
        # Fetch user details needed for verification
        user_details = get_verification_details(email)
        
        if not user_details:
            flash('User not found or error fetching details.', 'error')
            return render_template('verify.html', form=form, email=email)

        user_id, is_verified, stored_code, expires_at = user_details

        if is_verified:
             flash('Your account is already verified. Please login.', 'info')
             return redirect(url_for('auth.login'))

        if not stored_code or not expires_at:
             flash('Verification code not set or expired. Please register again or request resend.', 'error')
             # TODO: Implement resend logic later
             return render_template('verify.html', form=form, email=email)

        # Check expiration (ensure expires_at is timezone-aware)
        if expires_at.tzinfo is None:
             # Attempt to make it offset-aware assuming UTC if naive
             expires_at = expires_at.replace(tzinfo=timezone.utc)
             print(f"Warning: Verification expiry for {email} was timezone-naive. Assumed UTC.")
             
        if datetime.now(timezone.utc) > expires_at:
            flash('Verification code has expired. Please request a new one.', 'error')
            # TODO: Implement resend logic later
            return render_template('verify.html', form=form, email=email)
            
        # Check code match
        if stored_code == submitted_code:
            # Success! Verify user in DB
            success = verify_user(user_id)
            if success:
                flash('Email verified successfully! You are now logged in.', 'success')
                # Log the user in manually after verification
                db_user = get_user_by_id(user_id) # Fetch full user data again
                if db_user:
                     user = User(id=db_user[0], username=db_user[1], password_hash=db_user[2],
                                 google_id=db_user[3], tokens_used=db_user[4], is_subscribed=db_user[5],
                                 last_token_reset=db_user[6],
                                 first_name=db_user[7], last_name=db_user[8], email=db_user[9], is_verified=db_user[10])
                     login_user(user) # Use Flask-Login to log them in
                     return redirect(url_for('index'))
                else:
                     flash('Verification successful, but failed to log you in. Please login manually.', 'warning')
                     return redirect(url_for('auth.login'))
            else:
                flash('An error occurred during verification. Please try again.', 'error')
        else:
            flash('Invalid verification code.', 'error')

    # GET request or failed POST validation
    return render_template('verify.html', form=form, email=email)

# --- NEW Resend Verification Route ---
@_auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email')
    if not email:
        flash('Email address missing.', 'error')
        return redirect(url_for('auth.login')) # Or maybe to register?

    user_details = get_verification_details(email)
    if not user_details:
        flash(f'No account found for {email}.', 'warning')
        return redirect(url_for('auth.register'))
    
    user_id, is_verified, _, _ = user_details # Unpack needed parts

    if is_verified:
        flash('Account is already verified.', 'info')
        # Log them in if not already? For now, just redirect.
        return redirect(url_for('auth.login'))
    
    # Proceed with resending
    try:
        verification_code = "".join(random.choices(string.digits, k=4))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        set_code_success = set_verification_code(user_id, verification_code, expires_at)

        if set_code_success:
            send_verification_email(email, verification_code)
            flash(f'A new verification code has been sent to {email}.', 'info')
        else:
            flash('Failed to update verification code. Please try again later.', 'error')
    except Exception as e:
        print(f"Error during resend verification for {email}: {e}", file=sys.stderr)
        traceback.print_exc()
        flash('An error occurred while trying to resend the verification code.', 'error')
    
    # Redirect back to the verification page regardless of success/failure
    return redirect(url_for('auth.verify_email', email=email))

# --- TODO: Add Verification Route --- 