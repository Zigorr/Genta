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
    """Initializes the database and creates/updates the users table step-by-step."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Failed to get DB connection for init_db.", file=sys.stderr)
        return # Cannot proceed

    try:
        # Use a single cursor
        with conn.cursor() as cur:

            # Step 1: Create Table
            try:
                print("Step 1: Creating users table if it doesn't exist...")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT, google_id TEXT UNIQUE,
                    tokens_used INTEGER DEFAULT 0 NOT NULL, is_subscribed BOOLEAN DEFAULT FALSE NOT NULL,
                    CONSTRAINT password_or_google_id CHECK (password_hash IS NOT NULL OR google_id IS NOT NULL)
                );
                """)
                conn.commit() # Commit this step
                print("Step 1: Completed.")
            except Exception as e:
                print(f"Error during Step 1 (Create Table): {e}")
                conn.rollback() # Rollback this step
                raise # Re-raise to stop initialization

            # Step 2: Create Indices
            try:
                print("Step 2: Creating indices...")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users (google_id);")
                conn.commit() # Commit this step
                print("Step 2: Completed.")
            except Exception as e:
                print(f"Error during Step 2 (Create Indices): {e}")
                conn.rollback()
                # Decide if index failure is critical - perhaps log and continue?
                # For now, let's raise to be safe
                raise

            # Step 3: Add google_id column
            try:
                print("Step 3: Ensuring google_id column exists...")
                _add_column_if_not_exists(cur, 'users', 'google_id', 'TEXT UNIQUE')
                conn.commit() # Commit this step
                print("Step 3: Completed.")
            except Exception as e:
                print(f"Error during Step 3 (Add google_id): {e}")
                conn.rollback()
                raise

            # Step 4: Alter password_hash nullability
            try:
                print("Step 4: Ensuring password_hash column allows NULLs...")
                _alter_column_nullability(cur, 'users', 'password_hash', True)
                conn.commit() # Commit this step
                print("Step 4: Completed.")
            except Exception as e:
                # Check if the error is harmless (e.g., already nullable)
                # psycopg2 error for trying to drop NOT NULL when already nullable might be specific
                # For now, log and potentially continue if altering null fails, 
                # as the app logic might handle it.
                print(f"Warning during Step 4 (Alter password_hash): {e}")
                conn.rollback() # Rollback the failed alter attempt
                # Decide whether to continue or raise; let's continue for now.
                # raise

            # Step 5: Add tokens_used column
            try:
                print("Step 5: Ensuring tokens_used column exists...")
                _add_column_if_not_exists(cur, 'users', 'tokens_used', 'INTEGER DEFAULT 0 NOT NULL')
                conn.commit() # Commit this step
                print("Step 5: Completed.")
            except Exception as e:
                print(f"Error during Step 5 (Add tokens_used): {e}")
                conn.rollback()
                raise

            # Step 6: Add is_subscribed column
            try:
                print("Step 6: Ensuring is_subscribed column exists...")
                _add_column_if_not_exists(cur, 'users', 'is_subscribed', 'BOOLEAN DEFAULT FALSE NOT NULL')
                conn.commit() # Commit this step
                print("Step 6: Completed.")
            except Exception as e:
                print(f"Error during Step 6 (Add is_subscribed): {e}")
                conn.rollback()
                raise

            print("Database schema fully checked/updated.")

    except Exception as e:
        # This catches errors re-raised from the inner steps
        print(f"ERROR during database initialization sequence: {e}", file=sys.stderr)
        traceback.print_exc()
        # No need to rollback here, inner steps handle it before raising

    finally:
        if conn:
            release_db_connection(conn)

def _add_column_if_not_exists(cursor, table, column, col_type):
    """Helper to add a column if it doesn't exist. Lets errors propagate."""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1;")
        print(f"Column '{column}' already exists.") # Added log
    except (psycopg2.errors.UndefinedColumn, sqlite3.OperationalError):
        print(f"Column '{column}' not found, adding...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
        print(f"Added column '{column}'.")
    # Let other potential errors (e.g., during ALTER) propagate

def _alter_column_nullability(cursor, table, column, allow_null):
    """Helper to change nullability (PostgreSQL only). Lets errors propagate."""
    if not IS_POSTGRES:
        return
    if allow_null:
        # This might fail if already nullable, but we catch it in init_db now
        print(f"Attempting to allow NULLs for {column}...")
        cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL;")
        print(f"Allowed NULLs for column '{column}'.")
    # else: pass (don't handle SET NOT NULL for now)

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