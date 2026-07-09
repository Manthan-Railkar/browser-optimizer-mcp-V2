"""
SQLite database module for persistent caching.
Replaces the in-memory TTLCache with a persistent store that survives process restarts.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple
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
                    hit_count INTEGER DEFAULT 0,
                    embedding TEXT
                )
            ''')
            # Migration: add embedding column if missing (existing databases)
            try:
                conn.execute("ALTER TABLE cache ADD COLUMN embedding TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
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

    def set(self, key: str, value: Any, embedding: Optional[List[float]] = None):
        """
        Store an item in the cache with an optional structural embedding.
        """
        value_str = json.dumps(value)
        embedding_str = json.dumps(embedding) if embedding is not None else None
        created_at = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO cache (key, value, created_at, ttl, hit_count, embedding)
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    created_at=excluded.created_at,
                    ttl=excluded.ttl,
                    hit_count=0,
                    embedding=excluded.embedding
            ''', (key, value_str, created_at, self.ttl, embedding_str))
            conn.commit()

    def __setitem__(self, key: str, value: Any):
        """
        Store an item in the cache (dict-style, without embedding).
        """
        self.set(key, value)

    def get_all_embeddings(self) -> List[Tuple[str, List[float], Any]]:
        """
        Retrieve all non-expired entries that have an embedding stored.

        Returns:
            List of (key, embedding, value) tuples.
        """
        self.purge_expired()
        results = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT key, embedding, value FROM cache WHERE embedding IS NOT NULL"
            )
            for row in cursor.fetchall():
                key, emb_str, val_str = row
                try:
                    embedding = json.loads(emb_str)
                    value = json.loads(val_str)
                    results.append((key, embedding, value))
                except (json.JSONDecodeError, TypeError):
                    continue
        return results

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
