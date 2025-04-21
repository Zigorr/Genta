# UserSettings/__init__.py
from flask import Blueprint

# Define the blueprint: 'settings' is the name,
# __name__ helps determine root path, url_prefix adds /settings to routes
settings_bp = Blueprint('settings', __name__, url_prefix='/settings', template_folder='../templates')

# Import routes after blueprint definition to avoid circular imports
from . import routes 