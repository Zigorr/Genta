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
import datetime # Needed for timestamps

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
    """Initializes the database: Creates table if not exists, then ensures all columns/indices exist."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Failed to get DB connection for init_db.", file=sys.stderr)
        return

    try:
        # Use a single cursor for setup, manage commits per logical step
        with conn.cursor() as cur:

            # Step 1: Create Table with full schema IF NOT EXISTS
            print("Step 1: Ensuring users table exists with initial schema...")
            try:
                # Define the ideal final schema here
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT,
                    google_id TEXT UNIQUE, tokens_used INTEGER DEFAULT 0 NOT NULL,
                    is_subscribed BOOLEAN DEFAULT FALSE NOT NULL,
                    last_token_reset TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT password_or_google_id CHECK (password_hash IS NOT NULL OR google_id IS NOT NULL)
                );
                """)
                conn.commit() # Commit table creation attempt
                print("Step 1: Completed.")
            except Exception as e:
                print(f"Error during Step 1 (Create Table If Not Exists): {e}")
                conn.rollback()
                raise # Halt initialization if table creation fails

            # Step 2: Ensure all columns exist (Migration for older schemas)
            # Use ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+)
            # For SQLite or older PG, the _ensure_column_exists helper would need the old logic
            print("Step 2: Ensuring all columns exist...")
            columns_to_ensure = [
                ('google_id', 'TEXT UNIQUE'),
                ('tokens_used', 'INTEGER DEFAULT 0 NOT NULL'),
                ('is_subscribed', 'BOOLEAN DEFAULT FALSE NOT NULL'),
                ('last_token_reset', 'TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL')
            ]
            if IS_POSTGRES: # Assumes PG 9.6+
                 for col_name, col_type in columns_to_ensure:
                     try:
                         print(f"  Ensuring column {col_name}...")
                         cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                         conn.commit() # Commit each ADD COLUMN attempt
                     except Exception as e:
                         print(f"Error adding column {col_name}: {e}")
                         conn.rollback()
                         raise # Halt if adding a column fails
            else:
                 # Fallback for SQLite - requires the more complex helper
                 print("  Using fallback method for ensuring columns exist (SQLite)...")
                 for col_name, col_type in columns_to_ensure:
                      _ensure_column_exists_sqlite_safe(conn, cur, 'users', col_name, col_type)

            # Step 3: Ensure password_hash allows NULLs (Migration)
            _ensure_password_hash_nullable(conn, cur, 'users')
            print("Step 2 & 3: Column migration completed.")

            # Step 4: Ensure Indices Exist
            print("Step 4: Ensuring indices exist...")
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users (google_id);")
                conn.commit() # Commit index creation
                print("Step 4: Completed.")
            except Exception as e:
                print(f"Error during Step 4 (Create Indices): {e}")
                conn.rollback()
                raise # Halt if index creation fails

            # --- Chat History Table Setup (NEW) ---
            print("Step 5: Ensuring chat_history table exists...")
            try:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL, -- 'user', 'assistant', 'system', 'error'
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """)
                conn.commit()
                print("Step 5: chat_history table completed.")
            except Exception as e:
                print(f"Chat History Table Error: {e}")
                conn.rollback()
                raise

            # Step 6: Chat History Indices (NEW)
            print("Step 6: Ensuring chat_history indices exist...")
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_id_timestamp ON chat_history (user_id, timestamp DESC);")
                conn.commit()
                print("Step 6: chat_history indices completed.")
            except Exception as e:
                print(f"Chat History Indices Error: {e}")
                conn.rollback()
                raise

            print("Database schema initialization/migration complete.")

    except Exception as e:
        print(f"FATAL ERROR during database initialization sequence: {e}", file=sys.stderr)
        traceback.print_exc()
        # Ensure rollback happened if error occurred within try block
        if conn and not conn.closed:
            try: conn.rollback() # Attempt rollback if connection still open
            except Exception as rb_err: print(f"Error during final rollback: {rb_err}")

    finally:
        if conn:
            release_db_connection(conn)

# --- Helper functions for migration ---

# Simplified helper using ADD COLUMN IF NOT EXISTS (Requires PostgreSQL 9.6+)
# Note: This function is not explicitly called if IS_POSTGRES is true in init_db
# kept here for reference or potential direct use.
def _add_column_if_not_exists_pg96(conn, cursor, table, column, col_type):
    try:
        print(f"Ensuring column {column} (PG 9.6+ method)...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type};")
        conn.commit()
    except Exception as e:
        print(f"Error adding column {column}: {e}")
        conn.rollback()
        raise

# Original helper for SQLite or older PostgreSQL
def _ensure_column_exists_sqlite_safe(conn, cursor, table, column, col_type):
    try:
        # Check if column exists
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1;")
        print(f"Column {column} exists.")
    except (psycopg2.UndefinedColumn, sqlite3.OperationalError):
        # Column doesn't exist, add it
        try:
            print(f"Adding column {column} (SQLite/fallback method)...")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
            conn.commit() # Commit this specific change
            print(f"Added column {column}.")
        except Exception as e:
            print(f"Failed to add column {column}: {e}")
            conn.rollback() # Rollback failed add
            raise # Propagate error
    except Exception as e:
         # Handle unexpected errors during the initial SELECT check
         print(f"Unexpected error checking column {column}: {e}")
         conn.rollback()
         raise

def _ensure_password_hash_nullable(conn, cursor, table):
    if not IS_POSTGRES:
        print("Note: Skipping password_hash nullability check for non-PostgreSQL DB.")
        return
    try:
        print("Ensuring password_hash allows NULLs...")
        cursor.execute("SELECT is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name='password_hash';", (table,))
        result = cursor.fetchone()
        if result and result[0] == 'NO':
            print("  Attempting to alter password_hash to allow NULLs...")
            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN password_hash DROP NOT NULL;")
            conn.commit() # Commit this specific change
            print("  Successfully altered password_hash.")
        elif result and result[0] == 'YES':
             print("  password_hash already allows NULLs.")
        else:
             print("  Could not determine password_hash nullability or column not found.")
    except Exception as e:
        print(f"Warning/Error checking/altering password_hash nullability: {e}")
        conn.rollback() # Rollback failed attempt
        # Continue initialization, as app logic might handle nulls
        # raise # Uncomment to halt initialization on failure

# --- User Data Model ---
class User(UserMixin):
    """Represents a user in the system, compatible with Flask-Login."""
    def __init__(self, id, username, password_hash=None, google_id=None, tokens_used=0, is_subscribed=False, last_token_reset=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.google_id = google_id
        self.tokens_used = tokens_used
        self.is_subscribed = is_subscribed
        self.last_token_reset = last_token_reset

    def get_id(self):
        # Flask-Login requires get_id to return a string
        return str(self.id)


# --- User Management Functions ---

def get_user_by_id(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed, last_token_reset FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()
    finally:
        release_db_connection(conn)


def get_user_by_username(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed, last_token_reset FROM users WHERE username = %s", (username,))
            return cur.fetchone()
    finally:
        release_db_connection(conn)


def get_user_by_google_id(google_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
             # Fetch all needed columns for User object, including new ones
            cur.execute("SELECT id, username, password_hash, google_id, tokens_used, is_subscribed, last_token_reset FROM users WHERE google_id = %s", (google_id,))
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
    except (psycopg2.UniqueViolation, sqlite3.IntegrityError) as e:
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
            cur.execute("SELECT tokens_used, is_subscribed, last_token_reset FROM users WHERE id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return {"tokens_used": result[0], "is_subscribed": result[1], "last_token_reset": result[2]}
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

# --- Chat History Functions (NEW) ---

def add_chat_message(user_id, role, content):
    """Adds a message to the chat history."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to add chat message.", file=sys.stderr)
        return False
    sql = "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (%s, %s, %s, %s)"
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, role, content, timestamp))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding chat message for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn:
            release_db_connection(conn)

def get_chat_history(user_id, limit=50):
    """Retrieves the most recent chat messages for a user."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to get chat history.", file=sys.stderr)
        return []
    # Fetch role, content, timestamp - adjust columns as needed
    sql = "SELECT role, content, timestamp FROM chat_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s"
    messages = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, limit))
            # Fetchall returns list of tuples
            results = cur.fetchall()
            # Convert to list of dicts for easier template use, reverse to show oldest first
            for row in reversed(results):
                messages.append({'role': row[0], 'content': row[1], 'timestamp': row[2]})
            return messages
    except Exception as e:
        print(f"Error fetching chat history for user {user_id}: {e}", file=sys.stderr)
        return [] # Return empty list on error
    finally:
        if conn:
            release_db_connection(conn)

# NEW function to update subscription status
def set_user_subscription(user_id, status):
    """Updates the subscription status for a user."""
    conn = get_db_connection()
    if not conn:
        print(f"ERROR: Could not get DB connection to update subscription for user {user_id}.", file=sys.stderr)
        return False
    sql = "UPDATE users SET is_subscribed = %s WHERE id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (status, user_id))
            conn.commit()
            print(f"Subscription status for user {user_id} set to {status}.")
            return True
    except Exception as e:
        print(f"Error updating subscription for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn:
            release_db_connection(conn)

# NEW function to reset tokens and update timestamp
def reset_tokens(user_id):
    conn = get_db_connection()
    if not conn: print(f"ERROR: Could not get DB connection to reset tokens for user {user_id}.", file=sys.stderr); return False
    sql = "UPDATE users SET tokens_used = 0, last_token_reset = CURRENT_TIMESTAMP WHERE id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            conn.commit()
            print(f"Tokens reset for user {user_id}.")
            return True
    except Exception as e:
        print(f"Error resetting tokens for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn: release_db_connection(conn) 