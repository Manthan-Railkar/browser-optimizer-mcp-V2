"""
Semantic Cache module.
Fingerprints HTML structure using xxhash and caches compressed context to skip redundant loads.
"""

import time
import xxhash
from cachetools import TTLCache
from typing import Dict, Any, Optional
from browser_optimizer.config.settings import settings
from browser_optimizer.utils.logger import logger

class SemanticCache:
    """
    In-memory caching system based on TTLCache.
    Associates URLs with structural HTML hashes to serve pre-compressed payloads on identical pages.
    """
    def __init__(self, enabled: Optional[bool] = None, ttl: Optional[int] = None, max_size: Optional[int] = None):
        # Local TTL Cache using settings.
        # Max size is number of pages, TTL is in seconds.
        self.enabled = settings.CACHE_ENABLED if enabled is None else enabled
        self.ttl = settings.CACHE_TTL if ttl is None else ttl
        self.max_size = settings.CACHE_MAX_SIZE if max_size is None else max_size
        
        self._cache = TTLCache(maxsize=self.max_size, ttl=self.ttl)
        # Maps URL to the last page hash to check for changes
        self._url_to_hash: Dict[str, str] = {}
        logger.info(f"Semantic Cache initialized: Enabled={self.enabled}, TTL={self.ttl}s, MaxSize={self.max_size}")

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
        Query the cache for a given URL and check if the current page HTML matches the cached hash.
        
        Args:
            url (str): Target URL key.
            current_html (str): Freshly extracted HTML string to compare signatures.
            
        Returns:
            dict, optional: Cached compressed context if matching, else None.
        """
        if not self.enabled:
            return None
            
        current_hash = self.generate_hash(current_html)
        cached_entry = self._cache.get(url)
        
        if cached_entry:
            cached_hash = cached_entry.get("hash")
            if cached_hash == current_hash:
                logger.info(f"Cache HIT for URL: {url}")
                return cached_entry.get("context")
            else:
                logger.info(f"Cache MISMATCH (HTML changed) for URL: {url}")
        else:
            logger.info(f"Cache MISS for URL: {url}")
            
        # Store the current hash to associate with the URL
        self._url_to_hash[url] = current_hash
        return None

    def store(self, url: str, html: str, compressed_context: Dict[str, Any]):
        """
        Store a compressed context payload along with the page's current HTML signature.
        
        Args:
            url (str): Target URL key.
            html (str): Fresh raw HTML markup to hash.
            compressed_context (dict): Compressed UI representation.
        """
        if not self.enabled:
            return
            
        page_hash = self.generate_hash(html)
        self._cache[url] = {
            "hash": page_hash,
            "context": compressed_context,
            "timestamp": time.time()
        }
        self._url_to_hash[url] = page_hash
        logger.info(f"Cached context for URL: {url} (Hash: {page_hash})")

    def clear(self):
        """
        Flush all items from the cache.
        """
        self._cache.clear()
        self._url_to_hash.clear()
        logger.info("Cache cleared")

# Shared semantic cache instance
semantic_cache = SemanticCache()

