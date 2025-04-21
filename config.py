# config.py
import os
from dotenv import load_dotenv
from datetime import timedelta

# Load .env file from the project root
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env')) # Ensure .env is loaded relative to project root

class Config:
    """Base configuration."""
    # Secret key for session management, CSRF protection, etc.
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'you-should-really-change-this-secret'

    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')

    # OpenAI API Key
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

    # Google OAuth Configuration
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')

    # Required for local testing over http for OAuthLib
    OAUTHLIB_INSECURE_TRANSPORT = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT') == '1'

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=5)
    SESSION_PERMANENT = True
    SESSION_REFRESH_EACH_REQUEST = True

    # Basic Flask settings
    DEBUG = False
    TESTING = False

    # Free Tier Configuration
    FREE_TIER_TOKEN_LIMIT = int(os.getenv("FREE_TIER_TOKEN_LIMIT", 200))
    TOKEN_RESET_INTERVAL_MINUTES = int(os.getenv("TOKEN_RESET_INTERVAL_MINUTES", 5))

    # Stripe Configuration
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID') # Your $9.99/month Price ID
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') # For verifying webhooks

    # Email Configuration (for Flask-Mail)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') # e.g., 'smtp.googlemail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587) # Default to 587 (TLS)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    # IMPORTANT: Use environment variables for credentials!
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME # Default sender email
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL') # Optional: Admin email for error reports

    @staticmethod
    def init_app(app):
        # Perform any initialization based on config if needed
        if not Config.SECRET_KEY or Config.SECRET_KEY == 'you-should-really-change-this-secret':
            print("WARNING: SECRET_KEY is not set or is using the default value. Set a strong secret key in your environment.", file=os.sys.stderr)
        if not Config.DATABASE_URL:
            print("ERROR: DATABASE_URL environment variable not set.", file=os.sys.stderr)
            # Optionally raise an exception or exit
        if not Config.OPENAI_API_KEY:
            print("ERROR: OPENAI_API_KEY environment variable not set.", file=os.sys.stderr)
            # Optionally raise an exception or exit
        if not Config.GOOGLE_OAUTH_CLIENT_ID or not Config.GOOGLE_OAUTH_CLIENT_SECRET:
             print("WARNING: GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET not set. Google Login will fail.", file=os.sys.stderr)
        if not Config.STRIPE_SECRET_KEY or not Config.STRIPE_PUBLISHABLE_KEY:
             print("WARNING: Stripe API keys not fully configured. Payment integration will fail.", file=os.sys.stderr)
        if not Config.STRIPE_PRICE_ID:
             print("WARNING: Stripe Price ID not configured. Subscription checkout will fail.", file=os.sys.stderr)
        if not Config.STRIPE_WEBHOOK_SECRET:
             print("WARNING: Stripe Webhook Secret not configured. Subscription confirmation via webhook will fail.", file=os.sys.stderr)

        if Config.OAUTHLIB_INSECURE_TRANSPORT:
            os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
            print("WARNING: OAUTHLIB_INSECURE_TRANSPORT enabled for local HTTP testing.", file=os.sys.stderr)

        # Add checks/warnings for Mail config
        if not Config.MAIL_SERVER:
             print("WARNING: MAIL_SERVER not set. Email sending will fail.", file=os.sys.stderr)
        if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
             print("WARNING: MAIL_USERNAME or MAIL_PASSWORD not set. Email sending will fail.", file=os.sys.stderr)
        if not Config.MAIL_DEFAULT_SENDER:
             print("WARNING: MAIL_DEFAULT_SENDER not set. Using MAIL_USERNAME as default sender.", file=os.sys.stderr)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Optionally override DATABASE_URL for local dev if different from .env
    # DATABASE_URL = 'postgresql://user:pass@localhost/dev_db'

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    # Ensure insecure transport is OFF for production
    OAUTHLIB_INSECURE_TRANSPORT = False

    @classmethod
    def init_app(cls, app):
        Config.init_app(app) # Call base class init
        # Production specific checks or logging setup can go here
        if cls.OAUTHLIB_INSECURE_TRANSPORT:
             print("CRITICAL WARNING: OAUTHLIB_INSECURE_TRANSPORT is enabled in production!", file=os.sys.stderr)



config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 