from flask_mail import Message
from flask import current_app, url_for
from app.extensions import mail # Import mail from extensions
import threading

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            print(f"Verification email sent to {msg.recipients}")
        except Exception as e:
            print(f"Error sending email to {msg.recipients}: {e}")
            # Optionally log to a file or more robust error tracking

def send_verification_email(user_email, verification_code):
    app = current_app._get_current_object() # Get the real app instance
    subject = "Verify Your Email Address"
    sender = app.config.get('MAIL_DEFAULT_SENDER')
    verify_url = url_for('auth.verify_email', _external=True) # Assuming route name 'verify_email'
    
    # Consider using render_template for richer HTML emails later
    body = f"""Welcome!

Please use the following code to verify your email address:

{verification_code}

You can enter this code on the verification page: {verify_url}

This code will expire in 15 minutes.

If you did not register for this account, please ignore this email.
"""
    
    msg = Message(subject, sender=sender, recipients=[user_email], body=body)
    
    # Send email asynchronously in a separate thread
    thr = threading.Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr # Optional: return thread if you need to join it later 