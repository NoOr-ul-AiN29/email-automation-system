# logger.py
# -------------------------------------------------------
# PURPOSE:
#   Read and write email records to a JSON history file.
#
#   On Vercel (Linux): uses /tmp/email_history.json
#   On Windows (local dev): uses email_history.json in the project folder
# -------------------------------------------------------

import json
import os
import shutil
from datetime import datetime, timezone

# -------------------------------------------------------
# Pick the right storage path based on the OS
# On Vercel/Linux: /tmp is the only writable directory
# On Windows: just use the project folder directly
# -------------------------------------------------------
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(BASE_DIR, "email_history.json")

if os.name == "nt":
    # Windows — write directly to project folder
    HISTORY_FILE = SEED_FILE
else:
    # Linux / Vercel — write to /tmp
    HISTORY_FILE = "/tmp/email_history.json"


def _ensure_file() -> None:
    """Make sure the history file exists. Create it if not."""
    if not os.path.exists(HISTORY_FILE):
        try:
            # Try to copy the seed file first
            if os.path.exists(SEED_FILE):
                shutil.copy(SEED_FILE, HISTORY_FILE)
            else:
                # Create a fresh empty file
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f)
        except Exception as e:
            print(f"[logger] WARNING: Could not create history file: {e}")
            # Last resort — create empty file
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)


def load_history() -> list[dict]:
    """
    Load and return all email records from history.

    Returns:
        List of email record dicts.
    """
    _ensure_file()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_record(record: dict) -> None:
    """
    Append a new email record to the history file.

    Args:
        record: Dict with email details.
    """
    history = load_history()
    history.append(record)
    _write(history)


def update_record(record_id: str, updates: dict) -> bool:
    """
    Find a record by ID and apply updates.

    Args:
        record_id: UUID string of the record to update.
        updates:   Dict of fields to update.

    Returns:
        True if found and updated, False if not found.
    """
    history = load_history()
    for i, rec in enumerate(history):
        if rec.get("id") == record_id:
            history[i].update(updates)
            _write(history)
            return True
    return False


def get_pending() -> list[dict]:
    """
    Return all emails with status='scheduled' whose time has passed.

    Returns:
        List of email records that are due to be sent now.
    """
    history = load_history()
    now     = datetime.now(timezone.utc)
    pending = []

    for rec in history:
        if rec.get("status") != "scheduled":
            continue
        try:
            scheduled_at = datetime.fromisoformat(rec["scheduled_at"])
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at <= now:
                pending.append(rec)
        except (KeyError, ValueError):
            continue

    return pending


def _write(history: list[dict]) -> None:
    """Write the full history list back to the history file."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[logger] ERROR writing history: {e}")