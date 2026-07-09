"""
SQLite database module for persistent caching.
Replaces the in-memory TTLCache with a persistent store that survives process restarts.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Optional
from browser_optimizer.utils.logger import logger

class SQLiteCache:
    """
    A dictionary-like interface over an SQLite database to act as a persistent TTL cache.
    """
    def __init__(self, db_path: str = "cache.db", ttl: int = 300):
        self.db_path = db_path
        self.ttl = ttl
        self._init_db()
        self.purge_expired()

    def _init_db(self):
        """Initialize the SQLite schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at REAL,
                    ttl REAL,
                    hit_count INTEGER DEFAULT 0
                )
            ''')
            conn.commit()

    def get(self, key: str, default: Any = None) -> Optional[Any]:
        """
        Retrieve an item from the cache. Purges expired items before lookup.
        Increments the hit count if the item is found.
        """
        self.purge_expired()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value, hit_count FROM cache WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                value_str, hit_count = row
                # Increment hit_count
                conn.execute("UPDATE cache SET hit_count = ? WHERE key = ?", (hit_count + 1, key))
                conn.commit()
                return json.loads(value_str)
        return default

    def __setitem__(self, key: str, value: Any):
        """
        Store an item in the cache.
        """
        value_str = json.dumps(value)
        created_at = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO cache (key, value, created_at, ttl, hit_count)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    created_at=excluded.created_at,
                    ttl=excluded.ttl,
                    hit_count=0
            ''', (key, value_str, created_at, self.ttl))
            conn.commit()

    def clear(self):
        """
        Clear all entries from the cache.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache")
            conn.commit()

    def purge_expired(self):
        """
        Remove entries that have exceeded their TTL.
        """
        current_time = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE created_at + ttl < ?", (current_time,))
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Purged {deleted} expired cache entries.")
            conn.commit()
