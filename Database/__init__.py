# Database/__init__.py

# Import key components from the Database.py module to expose them at the package level
from .Database import (
    User,
    init_db,
    close_db_pool,
    get_db_connection, # Expose if needed directly elsewhere, though less likely now
    return_db_connection,
    get_user_by_id,
    get_user_by_username,
    get_user_by_google_id,
    add_user
)

# Add other exports if necessary 