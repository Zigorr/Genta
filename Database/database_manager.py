# Database/database_manager.py
import os
import sys
import psycopg2
from psycopg2 import pool
from flask import current_app # Import current_app
from flask_login import UserMixin # Needed for the User class
# Removed load_dotenv, config loaded by app factory
# from dotenv import load_dotenv

# --- Configuration & Constants ---
# load_dotenv(override=True) # Removed
# DATABASE_URL = os.getenv("DATABASE_URL") # Removed

# --- Database Setup ---
db_pool = None

def get_db_connection():
    """Gets a connection from the pool."""
    global db_pool
    if db_pool is None:
        # Get DATABASE_URL from Flask app config
        database_url = current_app.config.get('DATABASE_URL')
        if not database_url:
            # Log error using current_app logger if available, or print
            log_msg = "Error: DATABASE_URL not found in Flask app configuration."
            try: current_app.logger.error(log_msg)
            except RuntimeError: print(log_msg, file=sys.stderr)
            return None
        try:
            print("Initializing database connection pool...")
            db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=database_url)
            print("Database connection pool initialized.")
        except (Exception, psycopg2.DatabaseError) as error:
            log_msg = f"Error while initializing database pool: {error}"
            try: current_app.logger.error(log_msg)
            except RuntimeError: print(log_msg, file=sys.stderr)
            return None

    # Get a connection from the pool
    try:
        conn = db_pool.getconn()
        if not conn:
            print("Error: Failed to get connection from pool.", file=sys.stderr)
            return None # Or raise an exception
        return conn
    except (Exception, psycopg2.pool.PoolError) as error:
         print(f"Error getting connection from pool: {error}", file=sys.stderr)
         return None


def return_db_connection(conn):
    """Returns a connection to the pool."""
    if db_pool and conn:
        try:
            db_pool.putconn(conn)
        except (Exception, psycopg2.pool.PoolError) as error:
             print(f"Error returning connection to pool: {error}", file=sys.stderr)


def close_db_pool():
    """Closes all connections in the pool."""
    global db_pool
    if db_pool:
        print("Closing database connection pool.")
        db_pool.closeall()
        db_pool = None


def init_db():
    """Initializes the database (creates table and ensures columns exist)."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            print("Failed to get DB connection for init_db.", file=sys.stderr)
            return # Cannot proceed without connection

        cur = conn.cursor()
        print("Creating users table if it doesn't exist...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NULL -- Initially allow NULL
            );
        """)
        print("Users table checked/created.")

        # Ensure necessary columns exist and constraints are correct
        print("Ensuring google_id column exists...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE NULL;")
        print("Ensuring password_hash column allows NULLs...")
        cur.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;") # Or SET NULL if DROP NOT NULL fails

        conn.commit() # Commit all schema changes together
        print("Database schema checked/updated.")
    except (Exception, psycopg2.DatabaseError) as error:
        # Handle potential error if password_hash column didn't exist to be altered
        # Or if the DROP NOT NULL failed because it was already nullable (this is harmless)
        # Check specific SQLSTATE code for Undefined Column (42703)
        if hasattr(error, 'pgcode') and error.pgcode == '42703':
            print(f"Warning during schema update (column likely didn't exist for ALTER): {error}")
            if conn: conn.rollback() # Rollback the failed ALTER
            # Optionally, try adding the column if it was the missing one
            # But for now, just logging is safer.
        elif "already allows null values" in str(error) or "does not exist" in str(error):
             print(f"Info: Non-critical error during ALTER TABLE (likely already nullable or column missing for alter): {error}")
             if conn: conn.rollback() # Important: Rollback failed ALTER, but let CREATE/prior ALTER stand if they succeeded
             conn.commit() # Re-commit any prior successful changes in the try block
        else:
            print(f"Error during database schema update: {error}", file=sys.stderr)
            if conn: conn.rollback() # Rollback on other errors
    finally:
        if cur: cur.close()
        if conn: return_db_connection(conn)


# --- User Data Model ---
class User(UserMixin):
    """Represents a user in the system, compatible with Flask-Login."""
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash


# --- User Management Functions ---

def get_user_by_id(user_id):
    """Fetches a user from the database by their ID."""
    conn = None
    cur = None
    user_data = None
    try:
        conn = get_db_connection()
        if not conn: return None
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash FROM users WHERE id = %s", (user_id,))
        user_data = cur.fetchone()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error fetching user by ID: {error}", file=sys.stderr)
    finally:
        if cur: cur.close()
        if conn: return_db_connection(conn)
    # Return tuple directly (id, username, password_hash) or None
    return user_data


def get_user_by_username(username):
    """Fetches a user from the database by their username."""
    conn = None
    cur = None
    user_data = None
    try:
        conn = get_db_connection()
        if not conn: return None
        cur = conn.cursor()
        # Select google_id as well
        cur.execute("SELECT id, username, password_hash, google_id FROM users WHERE username = %s", (username,))
        user_data = cur.fetchone()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error fetching user by username: {error}", file=sys.stderr)
    finally:
        if cur: cur.close()
        if conn: return_db_connection(conn)
    # Return tuple directly (id, username, password_hash, google_id) or None
    return user_data


def get_user_by_google_id(google_id):
    """Fetches a user from the database by their Google ID."""
    conn = None
    cur = None
    user_data = None
    try:
        conn = get_db_connection()
        if not conn: return None
        cur = conn.cursor()
        # Select all needed fields for the User object
        cur.execute("SELECT id, username, password_hash FROM users WHERE google_id = %s", (google_id,))
        user_data = cur.fetchone()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error fetching user by Google ID: {error}", file=sys.stderr)
    finally:
        if cur: cur.close()
        if conn: return_db_connection(conn)
    return user_data


def add_user(username, password_hash=None, google_id=None):
    """Adds a new user to the database. Can handle regular or OAuth users."""
    conn = None
    cur = None
    success = False
    new_user_id = None # To return the ID of the newly created user
    try:
        conn = get_db_connection()
        if not conn: return False, None
        cur = conn.cursor()
        # Use RETURNING id to get the new user's ID
        cur.execute("INSERT INTO users (username, password_hash, google_id) VALUES (%s, %s, %s) RETURNING id",
                    (username, password_hash, google_id))
        new_user_id = cur.fetchone()[0] # Get the returned ID
        conn.commit()
        success = True
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error adding user: {error}", file=sys.stderr)
        if conn: conn.rollback() # Rollback on error
    finally:
        if cur: cur.close()
        if conn: return_db_connection(conn)
    return success, new_user_id # Return success status and the new user's ID 