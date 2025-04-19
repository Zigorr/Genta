# Database/database_manager.py
import os
import sys
import psycopg2
from psycopg2 import pool
from flask import current_app # Import current_app
from flask_login import UserMixin # Needed for the User class
# Removed load_dotenv, config loaded by app factory
# from dotenv import load_dotenv
import sqlite3
import traceback

# --- Configuration & Constants ---
# load_dotenv(override=True) # Removed
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///mydatabase.db") # Default to SQLite if not set
IS_POSTGRES = DATABASE_URL.startswith("postgres")

# --- Database Setup ---
pool = None

def init_connection_pool():
    global pool
    if IS_POSTGRES and not pool:
        try:
            print("Initializing database connection pool...")
            # Ensure max_connections is reasonable, e.g., 5-10 for most apps
            pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
            print("Database connection pool initialized.")
        except psycopg2.OperationalError as e:
            print(f"ERROR: Could not connect to PostgreSQL database: {e}", file=sys.stderr)
            # Optionally exit or raise a custom exception if DB is critical at startup
            # sys.exit(1)
            pool = None # Ensure pool is None if init fails
        except Exception as e:
            print(f"ERROR: Unexpected error initializing connection pool: {e}", file=sys.stderr)
            pool = None
    elif not IS_POSTGRES:
        print("Using SQLite, connection pool not applicable.")

def get_db_connection():
    """Gets a connection from the pool (PostgreSQL) or creates one (SQLite)."""
    if IS_POSTGRES:
        if not pool:
            # Attempt to re-initialize if accessed before successful init or after failure
            init_connection_pool()
            if not pool:
                raise ConnectionError("Database connection pool is not available.")
        return pool.getconn()
    else:
        return sqlite3.connect(DATABASE_URL.split("///")[1]) # Get filename from URL

def release_db_connection(conn):
    """Releases a connection back to the pool (PostgreSQL) or closes it (SQLite)."""
    if IS_POSTGRES and pool:
        pool.putconn(conn)
    elif conn:
        conn.close()

def close_connection_pool():
    global pool
    if IS_POSTGRES and pool:
        print("Closing database connection pool...")
        pool.closeall()
        pool = None
        print("Database connection pool closed.")


def init_db():
    """Initializes the database and creates the users table if it doesn't exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            print("Creating users table if it doesn't exist...")
            # Use TEXT for password_hash and google_id for flexibility
            # Add tokens_used and is_subscribed columns
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                google_id TEXT UNIQUE,
                tokens_used INTEGER DEFAULT 0 NOT NULL,
                is_subscribed BOOLEAN DEFAULT FALSE NOT NULL,
                CONSTRAINT password_or_google_id CHECK (password_hash IS NOT NULL OR google_id IS NOT NULL)
            );
            """)
            # Add indices for faster lookups
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users (google_id);")

            # Add columns if they don't exist (for existing databases)
            print("Ensuring google_id column exists...")
            _add_column_if_not_exists(cur, 'users', 'google_id', 'TEXT UNIQUE')

            print("Ensuring password_hash column allows NULLs...")
            _alter_column_nullability(cur, 'users', 'password_hash', True)

            print("Ensuring tokens_used column exists...")
            _add_column_if_not_exists(cur, 'users', 'tokens_used', 'INTEGER DEFAULT 0 NOT NULL')

            print("Ensuring is_subscribed column exists...")
            _add_column_if_not_exists(cur, 'users', 'is_subscribed', 'BOOLEAN DEFAULT FALSE NOT NULL')

            conn.commit()
            print("Database schema checked/updated.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR during database initialization: {e}", file=sys.stderr)
        traceback.print_exc()
    finally:
        release_db_connection(conn)

def _add_column_if_not_exists(cursor, table, column, col_type):
    """Helper to add a column if it doesn't exist."""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1;")
    except (psycopg2.errors.UndefinedColumn, sqlite3.OperationalError):
        # Column doesn't exist, add it
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
        print(f"Added column '{column}' to table '{table}'.")

def _alter_column_nullability(cursor, table, column, allow_null):
    """Helper to change nullability (PostgreSQL only for direct SET/DROP NOT NULL)."""
    if not IS_POSTGRES:
        # SQLite requires complex table rebuild, often easier to handle in model/app logic
        # print(f"Note: Altering NULL constraint on '{column}' for SQLite requires table rebuild.")
        return
    try:
        # Check current nullability (This is a bit complex, maybe just try the ALTER)
        # Instead, just try setting or dropping the constraint
        if allow_null:
            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL;")
            print(f"Allowed NULLs for column '{column}' in table '{table}'.")
        else:
            # Ensure existing NULLs are handled before adding NOT NULL
            cursor.execute(f"UPDATE {table} SET {column} = <default_value> WHERE {column} IS NULL;") # Replace <default_value> appropriately
            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;")
            print(f"Set NOT NULL for column '{column}' in table '{table}'.")
    except (psycopg2.errors.UndefinedColumn, psycopg2.errors.InvalidTableDefinition) as e:
         print(f"Could not alter nullability for {column}: {e}") # Might fail if column doesn't exist or other issues
    except psycopg2.errors.NotNullViolation as e:
         print(f"Could not SET NOT NULL for {column}, existing NULLs? Error: {e}")
    except Exception as e:
        print(f"Unexpected error altering nullability for {column}: {e}")

# --- User Data Model ---
class User(UserMixin):
    """Represents a user in the system, compatible with Flask-Login."""
    def __init__(self, id, username, password_hash=None, google_id=None, tokens_used=0, is_subscribed=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.google_id = google_id
        self.tokens_used = tokens_used
        self.is_subscribed = is_subscribed

    def get_id(self):
        # Flask-Login requires get_id to return a string
        return str(self.id)


# --- User Management Functions ---

def get_user_by_id(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()
    finally:
        release_db_connection(conn)


def get_user_by_username(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed FROM users WHERE username = %s", (username,))
            return cur.fetchone()
    finally:
        release_db_connection(conn)


def get_user_by_google_id(google_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
             # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed FROM users WHERE google_id = %s", (google_id,))
            return cur.fetchone()
    finally:
        release_db_connection(conn)


def add_user(username, password_hash=None, google_id=None):
    # Basic validation
    if not username or (password_hash is None and google_id is None):
        print("Error: Username and either password or google_id are required to add user.")
        return False, None

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Insert user with default values for new columns
            cur.execute("INSERT INTO users (username, password_hash, google_id) VALUES (%s, %s, %s) RETURNING id",
                        (username, password_hash, google_id))
            new_user_id = cur.fetchone()[0]
            conn.commit()
            return True, new_user_id # Return success and new ID
    except (psycopg2.errors.UniqueViolation, sqlite3.IntegrityError) as e:
        # Handle cases where username or google_id might already exist
        conn.rollback()
        print(f"Database integrity error adding user '{username}': {e}")
        return False, None # Indicate failure
    except Exception as e:
        conn.rollback()
        print(f"Unexpected error adding user '{username}': {e}")
        traceback.print_exc()
        return False, None # Indicate failure
    finally:
        release_db_connection(conn)


# NEW function to get specific user details needed for checks
def get_user_token_details(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tokens_used, is_subscribed FROM users WHERE id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return {"tokens_used": result[0], "is_subscribed": result[1]}
            else:
                return None # User not found
    except Exception as e:
        print(f"Error getting user token details for {user_id}: {e}")
        return None # Return None on error
    finally:
        release_db_connection(conn)


# NEW function to update token usage
def update_token_usage(user_id, tokens_increment):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Use atomic update
            cur.execute("UPDATE users SET tokens_used = tokens_used + %s WHERE id = %s", (tokens_increment, user_id))
            conn.commit()
            return True # Indicate success
    except Exception as e:
        conn.rollback()
        print(f"Error updating token usage for user {user_id}: {e}")
        return False # Indicate failure
    finally:
        release_db_connection(conn) 