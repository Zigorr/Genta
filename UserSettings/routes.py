# UserSettings/routes.py

from flask import render_template, url_for, redirect, current_app
from flask_login import login_required, current_user

from . import settings_bp
from Database.database_manager import get_chat_history, get_user_token_details

@settings_bp.route('/')
@login_required
def view_settings():
    """Displays the user settings page with account info and chat history."""
    user_id = current_user.id
    
    # Fetch user details (token usage, subscription status)
    user_details = get_user_token_details(user_id)
    if not user_details:
        # Handle error case where user details can't be fetched
        user_details = {'tokens_used': 'N/A', 'is_subscribed': False} # Provide defaults
        # Optionally flash a message

    # Fetch chat history
    chat_history = get_chat_history(user_id, limit=100) # Get last 100 messages
    
    # Get token limit from config
    token_limit = current_app.config.get('FREE_TIER_TOKEN_LIMIT', 200)

    return render_template('settings.html',
                           user=current_user, 
                           user_details=user_details,
                           token_limit=token_limit,
                           history=chat_history)

@settings_bp.route('/subscribe')
@login_required
def subscribe_page():
    """Placeholder route for the subscription page."""
    # In the future, this will integrate with a payment provider (e.g., Stripe)
    # For now, it can just render a simple template.
    return render_template('subscribe.html') 