"""
Semantic Cache module.
Fingerprints HTML structure using xxhash for exact matches, and falls back to
structural-embedding cosine similarity to recognise near-duplicate pages
(same template, different data).
"""

import time
import xxhash
from typing import Dict, Any, Optional, Tuple
from browser_optimizer.config.settings import settings
from browser_optimizer.utils.logger import logger
from browser_optimizer.cache.db import SQLiteCache
from browser_optimizer.cache.embedding import structural_embedding

class SemanticCache:
    """
    Persistent caching system backed by SQLite.
    Uses exact xxhash matching as the primary strategy, with structural-embedding
    cosine similarity as a fallback for near-duplicate page detection.
    """
    def __init__(self, enabled: Optional[bool] = None, ttl: Optional[int] = None, max_size: Optional[int] = None):
        self.enabled = settings.CACHE_ENABLED if enabled is None else enabled
        self.ttl = settings.CACHE_TTL if ttl is None else ttl
        self.max_size = settings.CACHE_MAX_SIZE if max_size is None else max_size
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD

        self._cache = SQLiteCache(ttl=self.ttl)
        # Maps URL to the last page hash to check for changes
        self._url_to_hash: Dict[str, str] = {}
        logger.info(
            f"Semantic Cache initialized: Enabled={self.enabled}, TTL={self.ttl}s, "
            f"MaxSize={self.max_size}, SimilarityThreshold={self.similarity_threshold}"
        )

    def generate_hash(self, text: str) -> str:
        """
        Generate a fast, non-cryptographic 64-bit signature of the HTML payload.
        
        Args:
            text (str): Raw target string.
            
        Returns:
            str: Hex digest fingerprint.
        """
        return xxhash.xxh64(text.encode('utf-8', errors='ignore')).hexdigest()

    def lookup(self, url: str, current_html: str) -> Optional[Dict[str, Any]]:
        """
        Query the cache using a two-tier strategy:

        1. **Exact hash match** — compare xxhash of the current HTML against the
           cached hash for this URL.  Fastest path.
        2. **Semantic similarity fallback** — if the exact hash misses, compute a
           structural embedding and cosine-similarity-scan all stored entries.
           If the best match exceeds ``SIMILARITY_THRESHOLD``, return the cached
           context tagged with ``semantic_match: True``.

        Args:
            url: Target URL key.
            current_html: Freshly extracted HTML string.

        Returns:
            Cached context dict (with an optional ``semantic_match`` flag), or None.
        """
        if not self.enabled:
            return None

        current_hash = self.generate_hash(current_html)
        cached_entry = self._cache.get(url)

        # ── Tier 1: exact hash match ──────────────────────────
        if cached_entry:
            cached_hash = cached_entry.get("hash")
            if cached_hash == current_hash:
                logger.info(f"Cache EXACT HIT for URL: {url}")
                return cached_entry.get("context")
            else:
                logger.info(f"Cache MISMATCH (HTML changed) for URL: {url}")
        else:
            logger.info(f"Cache MISS for URL: {url}")

        # ── Tier 2: semantic similarity fallback ──────────────
        semantic_result = self._semantic_lookup(current_html)
        if semantic_result is not None:
            matched_context, score, matched_url = semantic_result
            logger.info(
                f"Cache SEMANTIC HIT for URL: {url} "
                f"(matched {matched_url}, similarity={score:.4f})"
            )
            # Return the cached context annotated with the semantic match info
            ctx = dict(matched_context)  # shallow copy
            ctx["semantic_match"] = True
            ctx["similarity_score"] = round(score, 4)
            ctx["matched_url"] = matched_url
            return ctx

        # Store the current hash to associate with the URL
        self._url_to_hash[url] = current_hash
        return None

    def _semantic_lookup(
        self, current_html: str
    ) -> Optional[Tuple[Dict[str, Any], float, str]]:
        """
        Scan all cached embeddings for a near-duplicate structural match.

        Returns:
            A tuple of (cached_context, similarity_score, matched_url) if the
            best cosine similarity exceeds the threshold, else None.
        """
        current_embedding = structural_embedding.generate(current_html)
        entries = self._cache.get_all_embeddings()

        if not entries:
            return None

        best_score = -1.0
        best_context = None
        best_url = None

        for stored_url, stored_embedding, stored_value in entries:
            score = structural_embedding.cosine_similarity(
                current_embedding, stored_embedding
            )
            if score > best_score:
                best_score = score
                best_context = stored_value.get("context")
                best_url = stored_url

        if best_score >= self.similarity_threshold and best_context is not None:
            return (best_context, best_score, best_url)

        return None

    def store(self, url: str, html: str, compressed_context: Dict[str, Any]):
        """
        Store a compressed context payload along with the page's current HTML
        signature and its structural embedding.

        Args:
            url: Target URL key.
            html: Fresh raw HTML markup to hash and embed.
            compressed_context: Compressed UI representation.
        """
        if not self.enabled:
            return

        page_hash = self.generate_hash(html)
        embedding = structural_embedding.generate(html)

        entry = {
            "hash": page_hash,
            "context": compressed_context,
            "timestamp": time.time()
        }
        self._cache.set(url, entry, embedding=embedding)
        self._url_to_hash[url] = page_hash
        logger.info(f"Cached context for URL: {url} (Hash: {page_hash}, Embedding dim={len(embedding)})")

    def clear(self):
        """
        Flush all items from the cache.
        """
        self._cache.clear()
        self._url_to_hash.clear()
        logger.info("Cache cleared")

# Shared semantic cache instance
semantic_cache = SemanticCache()

