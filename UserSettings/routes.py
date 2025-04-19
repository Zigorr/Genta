# UserSettings/routes.py

import os # Added
import stripe # Added
from flask import render_template, url_for, redirect, current_app, flash, request, jsonify, abort # Added request, jsonify, abort
from flask_login import login_required, current_user

from . import settings_bp
from Database.database_manager import get_chat_history, get_user_token_details, set_user_subscription

# Configure Stripe API key on blueprint load (or app factory)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

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
    # Pass the publishable key to the template for Stripe.js
    publishable_key = current_app.config.get('STRIPE_PUBLISHABLE_KEY')
    return render_template('subscribe.html', stripe_publishable_key=publishable_key)

@settings_bp.route('/cancel_subscription', methods=['POST'])
@login_required
def cancel_subscription():
    """Simulates subscription cancellation and updates user status."""
    user_id = current_user.id
    success = set_user_subscription(user_id, False) # Set is_subscribed to False
    
    if success:
        flash('Subscription cancelled successfully. Access will revert to free tier after the current simulated period.', 'info')
    else:
        flash('An error occurred while cancelling your subscription. Please contact support.', 'error')
        
    # Redirect back to the main settings page to see the updated status
    return redirect(url_for('settings.view_settings'))

# --- Stripe Integration Routes ---

@settings_bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Creates a Stripe Checkout session for subscription."""
    price_id = current_app.config.get('STRIPE_PRICE_ID')
    if not stripe.api_key or not price_id:
        return jsonify({'error': 'Payment system not configured.'}), 500
        
    # Get base URL for success/cancel redirects
    # Use request.url_root which includes http/https and domain
    base_url = request.url_root 
    success_url = url_for('settings.view_settings', _external=True) # Redirect back to settings on success
    cancel_url = url_for('settings.subscribe_page', _external=True) # Redirect back to subscribe on cancel
    
    try:
        # Create a new Checkout Session for the subscription
        # Include the user ID in metadata to identify user in webhook
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}', # Optional: pass session id back
            cancel_url=cancel_url,
            # Pass user ID securely to identify user in webhook
            client_reference_id=str(current_user.id),
            # You can also prefill email:
            # customer_email=current_user.username, # Assuming username is email
        )
        # Return the Session ID to the frontend
        return jsonify({'sessionId': checkout_session.id})
    except Exception as e:
        print(f"Error creating Stripe checkout session: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Handles incoming webhooks from Stripe."""
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    if not webhook_secret:
        print("ERROR: Stripe webhook secret not configured.")
        return jsonify(success=False), 500

    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        print(f"Webhook error: Invalid payload - {e}")
        return jsonify(success=False), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print(f"Webhook error: Invalid signature - {e}")
        return jsonify(success=False), 400
    except Exception as e:
        print(f"Webhook error: Generic error - {e}")
        return jsonify(success=False), 500

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('client_reference_id')
        stripe_customer_id = session.get('customer')
        stripe_subscription_id = session.get('subscription') 

        if not user_id:
             print("Webhook Error: User ID not found in checkout session metadata.")
             return jsonify(success=False, error="Missing user ID"), 400
        
        print(f"Checkout session completed for user {user_id}")
        # Update user subscription status in your database
        success = set_user_subscription(int(user_id), True)
        if not success:
            print(f"Webhook Error: Failed to update subscription status for user {user_id}")
            # Consider queuing a retry or sending an alert
            return jsonify(success=False, error="Database update failed"), 500
        else:
             print(f"User {user_id} marked as subscribed.")
             # Optional: Store stripe_customer_id and stripe_subscription_id in your DB 
             # for future management (e.g., cancellations via API/portal)

    elif event['type'] == 'customer.subscription.deleted' or event['type'] == 'customer.subscription.updated':
        # Handle subscription cancellations or changes (e.g., user cancels in Stripe portal)
        session = event['data']['object']
        # You might need to look up the user based on stripe_customer_id if you stored it
        # stripe_customer_id = session.get('customer')
        # user = find_user_by_stripe_customer_id(stripe_customer_id)
        
        # For simplicity, we assume we don't track cancellations precisely here yet.
        # In a full implementation, you'd find the user and potentially set is_subscribed=False 
        # if session['status'] is now 'canceled' or session['cancel_at_period_end'] is true.
        print(f"Received subscription update/deleted event: {event['type']}")
        pass

    else:
        print(f"Unhandled Stripe event type: {event['type']}")

    return jsonify(success=True) 