# Database/database_manager.py
import os
import sys
import psycopg2
from psycopg2 import pool, errors
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

            # --- Step 5: Conversations Table (NEW) ---
            print("Step 5: Ensuring conversations table exists...")
            try:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """)
                conn.commit()
                 # Ensure title allows NULL (it does by default unless specified otherwise)
                # Ensure created_at/last_updated_at have defaults (they do)
                print("Step 5: conversations table completed.")
            except Exception as e:
                print(f"Conversations Table Error: {e}")
                conn.rollback()
                raise

            # --- Step 6: Conversations Indices (NEW) ---
            print("Step 6: Ensuring conversations indices exist...")
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id_last_updated ON conversations (user_id, last_updated_at DESC);")
                conn.commit()
                print("Step 6: conversations indices completed.")
            except Exception as e:
                print(f"Conversations Indices Error: {e}")
                conn.rollback()
                raise

            # --- Step 7: Chat History Table Update (Previously Step 5) ---
            print("Step 7: Ensuring chat_history table exists and has conversation_id...")
            try:
                # Create table if not exists (might already exist from previous runs)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL, -- Keep user_id for potential direct queries, though convo implies user
                    role TEXT NOT NULL, -- 'user', 'assistant', 'system', 'error'
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                    -- conversation_id added below if missing
                );
                """)
                conn.commit()

                # Add conversation_id column if it doesn't exist
                # Use ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+)
                if IS_POSTGRES:
                    cur.execute("""
                    ALTER TABLE chat_history
                    ADD COLUMN IF NOT EXISTS conversation_id INTEGER;
                    """)
                    conn.commit()
                    # Add the foreign key constraint AFTER the column exists
                    # Use a distinct constraint name to avoid conflicts if run multiple times
                    cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE constraint_name = 'fk_chat_history_conversation_id' AND table_name = 'chat_history'
                        ) THEN
                            ALTER TABLE chat_history
                            ADD CONSTRAINT fk_chat_history_conversation_id
                            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
                        END IF;
                    END $$;
                    """)
                    conn.commit()
                    # Update NULL conversation_id values to a placeholder or handle appropriately?
                    # For now, we'll require it to be NOT NULL going forward, new records must have it.
                    # We might need a migration step for old records if any exist.

                else: # SQLite - more complex ALTER TABLE
                    # Check if column exists
                    cur.execute("PRAGMA table_info(chat_history);")
                    columns = [info[1] for info in cur.fetchall()]
                    if 'conversation_id' not in columns:
                         print("  Adding conversation_id to chat_history (SQLite)...")
                         # SQLite requires table recreation for adding FK constraints easily
                         # This is complex and risky if data exists.
                         # For simplicity here, we'll add the column without enforcing FK if SQLite.
                         # A proper migration tool (like Alembic) would be better for production.
                         cur.execute("ALTER TABLE chat_history ADD COLUMN conversation_id INTEGER;")
                         conn.commit()
                         print("  Added conversation_id column (SQLite - FK not enforced by this script).")


                print("Step 7: chat_history table schema updated.")

            except Exception as e:
                print(f"Chat History Table Update Error: {e}")
                conn.rollback()
                raise

            # --- Step 8: Chat History Indices Update (Previously Step 6) ---
            print("Step 8: Ensuring updated chat_history indices exist...")
            try:
                # Remove old index if it exists (optional, but cleaner)
                # cur.execute("DROP INDEX IF EXISTS idx_chat_history_user_id_timestamp;")
                # Create new index including conversation_id
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_conversation_id_timestamp ON chat_history (conversation_id, timestamp DESC);")
                # Optional: Index for user_id lookup if still needed
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history (user_id);")

                conn.commit()
                print("Step 8: chat_history indices completed.")
            except Exception as e:
                print(f"Chat History Indices Update Error: {e}")
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
    except (psycopg2.DatabaseError, sqlite3.OperationalError) as e:
        # Check if it's an "undefined column" error (PostgreSQL code 42703)
        if IS_POSTGRES and hasattr(e, 'pgcode') and e.pgcode == '42703':
            # Column doesn't exist, add it
            try:
                print(f"Adding column {column} (PostgreSQL - UndefinedColumn detected)...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
                conn.commit()
                print(f"Added column {column}.")
            except Exception as add_e:
                print(f"Failed to add column {column}: {add_e}")
                conn.rollback()
                raise
        elif not IS_POSTGRES and isinstance(e, sqlite3.OperationalError) and "no such column" in str(e).lower():
             # Column doesn't exist in SQLite, add it
             try:
                print(f"Adding column {column} (SQLite - 'no such column' detected)...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
                conn.commit()
                print(f"Added column {column}.")
             except Exception as add_e:
                print(f"Failed to add column {column}: {add_e}")
                conn.rollback()
                raise
        else:
            # Different DB error, re-raise
            print(f"Unexpected database error checking column {column}: {e}")
            conn.rollback()
            raise
    except Exception as e:
         # Handle unexpected non-DB errors during the initial SELECT check
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
    except (psycopg2.IntegrityError, sqlite3.IntegrityError) as e:
        # Check if it's a unique violation (PostgreSQL code 23505)
        if (IS_POSTGRES and hasattr(e, 'pgcode') and e.pgcode == '23505') or \
           (not IS_POSTGRES and "unique constraint failed" in str(e).lower()):
            conn.rollback()
            print(f"Database integrity error adding user '{username}' (Unique Violation): {e}")
            return False, None
        else:
            # Different integrity error, handle or re-raise
            conn.rollback()
            print(f"Database integrity error adding user '{username}': {e}")
            return False, None
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

# --- Conversation Management Functions (NEW) ---

def create_conversation(user_id, title=None):
    """Creates a new conversation for a user and returns its ID."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to create conversation.", file=sys.stderr)
        return None
    # Generate a default title if none provided (e.g., based on timestamp)
    if not title:
        title = f"Chat from {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    sql = "INSERT INTO conversations (user_id, title, created_at, last_updated_at) VALUES (%s, %s, %s, %s) RETURNING id"
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, title, now, now))
            new_conversation_id = cur.fetchone()[0]
            conn.commit()
            print(f"Created conversation {new_conversation_id} for user {user_id}")
            return new_conversation_id
    except Exception as e:
        print(f"Error creating conversation for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return None
    finally:
        if conn:
            release_db_connection(conn)

def get_conversations_for_user(user_id):
    """Retrieves all conversations for a user, ordered by last updated."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to get conversations.", file=sys.stderr)
        return []
    # Fetch id, title, last_updated_at
    sql = "SELECT id, title, last_updated_at FROM conversations WHERE user_id = %s ORDER BY last_updated_at DESC"
    conversations = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            results = cur.fetchall()
            # Convert to list of dicts
            for row in results:
                conversations.append({'id': row[0], 'title': row[1], 'last_updated_at': row[2]})
            return conversations
    except Exception as e:
        print(f"Error fetching conversations for user {user_id}: {e}", file=sys.stderr)
        return [] # Return empty list on error
    finally:
        if conn:
            release_db_connection(conn)

def check_conversation_owner(conversation_id, user_id):
    """Checks if a given user owns the specified conversation. Returns boolean."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to check conversation owner.", file=sys.stderr)
        return False
    sql = "SELECT 1 FROM conversations WHERE id = %s AND user_id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (conversation_id, user_id))
            result = cur.fetchone()
            return result is not None # True if a row exists, False otherwise
    except Exception as e:
        print(f"Error checking conversation owner for convo {conversation_id}, user {user_id}: {e}", file=sys.stderr)
        return False
    finally:
        if conn:
            release_db_connection(conn)

def update_conversation_timestamp(conversation_id):
     """Updates the last_updated_at timestamp for a conversation."""
     conn = get_db_connection()
     if not conn:
         print("ERROR: Could not get DB connection to update conversation timestamp.", file=sys.stderr)
         return False
     sql = "UPDATE conversations SET last_updated_at = %s WHERE id = %s"
     now = datetime.datetime.now(datetime.timezone.utc)
     try:
         with conn.cursor() as cur:
             cur.execute(sql, (now, conversation_id))
             conn.commit()
             return True
     except Exception as e:
         print(f"Error updating timestamp for conversation {conversation_id}: {e}", file=sys.stderr)
         conn.rollback()
         return False
     finally:
         if conn:
             release_db_connection(conn)

def delete_conversation(conversation_id, user_id):
    """Deletes a conversation and its associated messages if the user owns it."""
    conn = get_db_connection()
    if not conn:
        print(f"ERROR: Could not get DB connection to delete conversation {conversation_id}.", file=sys.stderr)
        return False
    try:
        with conn.cursor() as cur:
            # Verify ownership before deleting
            cur.execute("SELECT 1 FROM conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id))
            if cur.fetchone() is None:
                print(f"Attempt to delete conversation {conversation_id} failed: Not owned by user {user_id} or does not exist.")
                return False # Or raise an exception for permission denied?

            # Delete the conversation (CASCADE should handle chat_history rows)
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            conn.commit()
            # Check if deletion happened (optional)
            rowcount = cur.rowcount
            print(f"Deleted conversation {conversation_id} owned by user {user_id}. Rows affected: {rowcount}")
            return rowcount > 0
    except Exception as e:
        print(f"Error deleting conversation {conversation_id} for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn:
            release_db_connection(conn)

# --- Chat History Functions (Modified) ---

def add_chat_message(user_id, conversation_id, role, content):
    """Adds a message to the chat history for a specific conversation."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to add chat message.", file=sys.stderr)
        return False

    # Ensure conversation_id is not None before inserting
    if conversation_id is None:
        print(f"ERROR: Attempted to add chat message with conversation_id=None for user {user_id}", file=sys.stderr)
        return False

    # Also update the conversation's last_updated_at timestamp
    if not update_conversation_timestamp(conversation_id):
        print(f"Warning: Failed to update timestamp for conversation {conversation_id} when adding message.", file=sys.stderr)
        # Continue adding the message anyway? Or return False? Let's continue for now.

    # Modified SQL to include conversation_id
    sql = "INSERT INTO chat_history (user_id, conversation_id, role, content, timestamp) VALUES (%s, %s, %s, %s, %s)"
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    try:
        with conn.cursor() as cur:
            # Pass conversation_id to execute
            cur.execute(sql, (user_id, conversation_id, role, content, timestamp))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding chat message for user {user_id}, convo {conversation_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn:
            release_db_connection(conn)

# Modified get_chat_history to fetch by conversation_id
def get_chat_history(conversation_id, limit=100): # Increased limit slightly
    """Retrieves the most recent chat messages for a specific conversation."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: Could not get DB connection to get chat history.", file=sys.stderr)
        return []

    # Ensure conversation_id is valid
    if conversation_id is None:
        print("ERROR: get_chat_history called with conversation_id=None.", file=sys.stderr)
        return []

    # Fetch role, content, timestamp - Filter by conversation_id
    # Removed user_id check here - ownership should be checked before calling this
    # NOTE: If using SQLite, placeholders might need to be '?' instead of '%s'
    sql = "SELECT id, user_id, conversation_id, role, content, timestamp FROM chat_history WHERE conversation_id = %s ORDER BY timestamp ASC LIMIT %s"
    messages = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (conversation_id, limit))
            # Fetchall returns list of tuples
            results = cur.fetchall()
            # Convert to list of dicts for easier template use
            # Keep ascending order as set in SQL
            for row in results:
                # Matching the expected tuple structure for template: (id, user_id, role, content, timestamp)
                # The template currently uses message[2] for role, message[3] for content.
                # Let's pass the full tuple to match the template's expectation for now.
                # A better approach would be to return dicts and update the template.
                 messages.append(row) # Pass the raw tuple
                # messages.append({'id': row[0], 'user_id': row[1], 'conversation_id': row[2], 'role': row[3], 'content': row[4], 'timestamp': row[5]})
            return messages
    except Exception as e:
        print(f"Error fetching chat history for conversation {conversation_id}: {e}", file=sys.stderr)
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

# --- Update Functions ---

def update_username(user_id, new_username):
    """Updates the username for a given user ID."""
    conn = get_db_connection()
    if not conn: return False
    sql = "UPDATE users SET username = %s WHERE id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (new_username.strip(), user_id))
            conn.commit()
            print(f"Username updated for user {user_id}.")
            return True
    except (psycopg2.IntegrityError, sqlite3.IntegrityError) as e: # Catch unique constraint violation
        # Check if it's a unique violation (PostgreSQL code 23505)
        if (IS_POSTGRES and hasattr(e, 'pgcode') and e.pgcode == '23505') or \
           (not IS_POSTGRES and "unique constraint failed" in str(e).lower()):
            print(f"Error updating username for user {user_id}: Username '{new_username}' likely already exists (Unique Violation). {e}")
            conn.rollback()
            return False
        else:
            # Different integrity error
            print(f"Error updating username for user {user_id}: {e}", file=sys.stderr)
            conn.rollback()
            return False
    except Exception as e:
        print(f"Error updating username for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False # Indicate general failure
    finally:
        if conn: release_db_connection(conn)

def update_password_hash(user_id, new_password_hash):
    """Updates the password hash for a given user ID."""
    conn = get_db_connection()
    if not conn: return False
    sql = "UPDATE users SET password_hash = %s WHERE id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (new_password_hash, user_id))
            conn.commit()
            print(f"Password updated for user {user_id}.")
            return True
    except Exception as e:
        print(f"Error updating password for user {user_id}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        if conn: release_db_connection(conn)

def get_password_hash(user_id):
    """Fetches only the password hash for a given user ID."""
    conn = get_db_connection()
    if not conn: return None
    sql = "SELECT password_hash FROM users WHERE id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Error fetching password hash for user {user_id}: {e}", file=sys.stderr)
        return None
    finally:
        if conn: release_db_connection(conn) 