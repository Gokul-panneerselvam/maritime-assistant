"""
SQLite Database Layer for Maritime Operations AI Agent.
Handles user authentication, conversation threads, message history, and audit logging.
"""

import os
import sqlite3
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_DIR = (Path(__file__).resolve().parents[2] / "storage").resolve()
CHECKPOINT_DIR = DB_DIR
DB_PATH = DB_DIR / "maritime_agent.db"


def get_db_connection() -> sqlite3.Connection:
    """Creates directory and returns an SQLite connection with Row row_factory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str) -> str:
    """Hashes a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return f"{salt.hex()}${pwd_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a password against the stored salt$hash string."""
    try:
        salt_hex, hash_hex = stored_hash.split('$')
        salt = bytes.fromhex(salt_hex)
        expected_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
        return expected_hash.hex() == hash_hex
    except Exception:
        return False


def init_db() -> None:
    """Initializes tables for users, threads, messages, and audit logs."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'fleet_dispatcher',
        created_at TEXT NOT NULL
    );
    """)

    # Conversation Threads Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS threads (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );
    """)

    # Messages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        structured_payload TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (thread_id) REFERENCES threads (thread_id) ON DELETE CASCADE
    );
    """)

    # Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        thread_id TEXT,
        user_query TEXT,
        cypher_queries TEXT,
        validation_status TEXT,
        latency_ms REAL,
        created_at TEXT NOT NULL
    );
    """)

    # Seed default maritime operations user if none exists
    cursor.execute("SELECT COUNT(*) as cnt FROM users;")
    row = cursor.fetchone()
    if row and row["cnt"] == 0:
        default_user_id = "user_ops_lead"
        cursor.execute("""
        INSERT INTO users (user_id, username, email, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            default_user_id,
            "maritime_lead",
            "ops@maritime-ops.com",
            hash_password("MaritimeOps2026!"),
            "Captain Alexander Vance",
            "fleet_superintendent",
            datetime.now(timezone.utc).isoformat()
        ))

    conn.commit()
    conn.close()


def create_user(username: str, email: str, password: str, full_name: str, role: str = "fleet_dispatcher") -> Optional[Dict[str, Any]]:
    """Registers a new user and returns user dictionary."""
    conn = get_db_connection()
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("""
        INSERT INTO users (user_id, username, email, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (user_id, username, email, hash_password(password), full_name, role, created_at))
        conn.commit()
        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
            "role": role,
            "created_at": created_at
        }
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate_user(username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticates against username or email and returns user dict if valid."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, username, email, password_hash, full_name, role, created_at
    FROM users
    WHERE username = ? OR email = ?;
    """, (username_or_email, username_or_email))
    row = cursor.fetchone()
    conn.close()

    if row and verify_password(password, row["password_hash"]):
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "created_at": row["created_at"]
        }
    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetches user details by user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, email, full_name, role, created_at FROM users WHERE user_id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def create_or_get_thread(thread_id: Optional[str], user_id: str, title: str = "New Maritime Inquiry") -> str:
    """Ensures thread exists; returns thread_id."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    if not thread_id:
        thread_id = f"thread_{uuid.uuid4().hex[:12]}"
        conn.execute("""
        INSERT INTO threads (thread_id, user_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?);
        """, (thread_id, user_id, title, now_iso, now_iso))
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT thread_id FROM threads WHERE thread_id = ?;", (thread_id,))
        if not cursor.fetchone():
            conn.execute("""
            INSERT INTO threads (thread_id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """, (thread_id, user_id, title, now_iso, now_iso))
        else:
            conn.execute("UPDATE threads SET updated_at = ? WHERE thread_id = ?;", (now_iso, thread_id))
    conn.commit()
    conn.close()
    return thread_id


def list_user_threads(user_id: str) -> List[Dict[str, Any]]:
    """Returns all threads belonging to a user ordered by most recently updated."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT thread_id, user_id, title, created_at, updated_at
    FROM threads
    WHERE user_id = ?
    ORDER BY updated_at DESC;
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_thread_title(thread_id: str, title: str) -> None:
    """Updates the display title of a thread."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE threads SET title = ?, updated_at = ? WHERE thread_id = ?;", (title, now_iso, thread_id))
    conn.commit()
    conn.close()


def save_message(thread_id: str, role: str, content: str, structured_payload: Optional[Dict[str, Any]] = None) -> str:
    """Saves a message turn into the thread history."""
    conn = get_db_connection()
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_str = json.dumps(structured_payload) if structured_payload else None
    conn.execute("""
    INSERT INTO messages (message_id, thread_id, role, content, structured_payload, created_at)
    VALUES (?, ?, ?, ?, ?, ?);
    """, (msg_id, thread_id, role, content, payload_str, now_iso))
    conn.execute("UPDATE threads SET updated_at = ? WHERE thread_id = ?;", (now_iso, thread_id))
    conn.commit()
    conn.close()
    return msg_id


def get_thread_history(thread_id: str) -> List[Dict[str, Any]]:
    """Fetches all messages in chronological order for a thread."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT message_id, thread_id, role, content, structured_payload, created_at
    FROM messages
    WHERE thread_id = ?
    ORDER BY created_at ASC;
    """, (thread_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        if item.get("structured_payload"):
            try:
                item["structured_payload"] = json.loads(item["structured_payload"])
            except Exception:
                pass
        result.append(item)
    return result


def log_audit_trail(user_id: Optional[str], thread_id: Optional[str], user_query: str,
                    cypher_queries: List[str], validation_status: str, latency_ms: float) -> None:
    """Logs an operational interaction for auditing and compliance."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute("""
    INSERT INTO audit_logs (user_id, thread_id, user_query, cypher_queries, validation_status, latency_ms, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (user_id, thread_id, user_query, json.dumps(cypher_queries), validation_status, latency_ms, now_iso))
    conn.commit()
    conn.close()


init_db()

