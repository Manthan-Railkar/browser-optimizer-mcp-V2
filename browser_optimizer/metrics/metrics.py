import threading
from typing import Dict, Any
from browser_optimizer.utils.logger import logger

class MetricsTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.raw_html_bytes = 0
        self.compressed_bytes = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.actions_executed = 0
        self.total_requests = 0

    def record_compression(self, raw_size: int, compressed_size: int):
        with self._lock:
            self.raw_html_bytes += raw_size
            self.compressed_bytes += compressed_size
            self.total_requests += 1
            
            savings = raw_size - compressed_size
            ratio = round((1 - compressed_size / raw_size) * 100, 1) if raw_size > 0 else 0
            logger.info(f"[METRICS] Saved {savings} bytes ({ratio}% reduction) on this request.")

    def record_cache_hit(self):
        with self._lock:
            self.cache_hits += 1
            logger.info("[METRICS] Cache HIT recorded")

    def record_cache_miss(self):
        with self._lock:
            self.cache_misses += 1
            logger.info("[METRICS] Cache MISS recorded")

    def record_action(self):
        with self._lock:
            self.actions_executed += 1
            logger.info("[METRICS] Action executed recorded")

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_saved = self.raw_html_bytes - self.compressed_bytes
            overall_ratio = round((1 - self.compressed_bytes / self.raw_html_bytes) * 100, 1) if self.raw_html_bytes > 0 else 0
            
            cache_total = self.cache_hits + self.cache_misses
            hit_rate = round((self.cache_hits / cache_total) * 100, 1) if cache_total > 0 else 0

            return {
                "total_requests": self.total_requests,
                "raw_html_size_total_bytes": self.raw_html_bytes,
                "compressed_size_total_bytes": self.compressed_bytes,
                "bytes_saved_total": total_saved,
                "overall_compression_ratio_pct": overall_ratio,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate_pct": hit_rate,
                "actions_executed": self.actions_executed
            }

metrics = MetricsTracker()
