# app/extensions.py
"""Initialize Flask extensions."""

from flask_login import LoginManager
from flask_mail import Mail

login_manager = LoginManager()
mail = Mail() 