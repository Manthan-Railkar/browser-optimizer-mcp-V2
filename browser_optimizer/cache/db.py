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

class MacroStore:
    """
    Persistent storage for recorded action macros (Skill-level caching).
    """
    def __init__(self, db_path: str = "cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS macros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    page_type TEXT,
                    sequence TEXT,
                    confidence REAL DEFAULT 1.0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0
                )
            ''')
            conn.commit()

    def save_macro(self, name: str, page_type: str, sequence: list) -> int:
        sequence_str = json.dumps(sequence)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO macros (name, page_type, sequence, confidence, success_count, fail_count)
                VALUES (?, ?, ?, 1.0, 0, 0)
            ''', (name, page_type, sequence_str))
            conn.commit()
            return cursor.lastrowid

    def list_macros(self, page_type: Optional[str] = None) -> list:
        with sqlite3.connect(self.db_path) as conn:
            if page_type:
                cursor = conn.execute("SELECT id, name, page_type, sequence, confidence, success_count, fail_count FROM macros WHERE page_type = ?", (page_type,))
            else:
                cursor = conn.execute("SELECT id, name, page_type, sequence, confidence, success_count, fail_count FROM macros")
            
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "page_type": r[2],
                    "sequence": json.loads(r[3]),
                    "confidence": r[4],
                    "success_count": r[5],
                    "fail_count": r[6]
                }
                for r in rows
            ]

    def get_macro(self, macro_id: int) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, name, page_type, sequence, confidence, success_count, fail_count FROM macros WHERE id = ?", (macro_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "page_type": row[2],
                    "sequence": json.loads(row[3]),
                    "confidence": row[4],
                    "success_count": row[5],
                    "fail_count": row[6]
                }
        return None

    def update_confidence(self, macro_id: int, success: bool):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT confidence, success_count, fail_count FROM macros WHERE id = ?", (macro_id,))
            row = cursor.fetchone()
            if row:
                confidence, success_count, fail_count = row
                if success:
                    success_count += 1
                    confidence = min(1.0, confidence + 0.1)
                else:
                    fail_count += 1
                    confidence = max(0.0, confidence - 0.2)
                
                conn.execute('''
                    UPDATE macros
                    SET confidence = ?, success_count = ?, fail_count = ?
                    WHERE id = ?
                ''', (confidence, success_count, fail_count, macro_id))
                conn.commit()

macro_store = MacroStore()
