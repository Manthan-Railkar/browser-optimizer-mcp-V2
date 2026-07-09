"""
Structural Embedding module.
Generates lightweight feature vectors from page DOM structure (tag counts, class
name fingerprints, DOM depth, attribute patterns) and provides brute-force cosine
similarity search for near-duplicate detection.

The embedding intentionally ignores text content — two pages with identical
structure but different data (e.g. product A vs product B) should produce
nearly identical embeddings.
"""

import math
from typing import List, Tuple, Optional, Dict, Any
from collections import Counter

import xxhash
from bs4 import BeautifulSoup

from browser_optimizer.utils.logger import logger

# ─────────────────────────────────────────────────────────────
# Feature dimensions
# ─────────────────────────────────────────────────────────────

# 30 common HTML tags whose normalised counts form the first part of the vector.
TAG_VOCABULARY = [
    "div", "span", "p", "a", "button", "input", "textarea", "select",
    "option", "form", "label", "img", "table", "tr", "td", "th",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "nav", "main", "aside",
]

TAG_DIM = len(TAG_VOCABULARY)       # 30
CLASS_BUCKETS = 32                  # hash-bucketed class-name distribution
DEPTH_DIM = 2                       # max depth, mean depth
ATTR_DIM = 4                        # count of elements with id / name / type / placeholder

EMBEDDING_DIM = TAG_DIM + CLASS_BUCKETS + DEPTH_DIM + ATTR_DIM  # 68


class StructuralEmbedding:
    """
    Generates a fixed-length numerical vector that captures the *structure* of
    an HTML page while ignoring its text content.
    """

    # ── public API ──────────────────────────────────────────

    def generate(self, html: str) -> List[float]:
        """
        Build a structural embedding from raw HTML.

        Args:
            html: Raw HTML markup string.

        Returns:
            A list of floats of length ``EMBEDDING_DIM``.
        """
        soup = BeautifulSoup(html, "lxml")
        all_tags = soup.find_all(True)  # every element node

        if not all_tags:
            return [0.0] * EMBEDDING_DIM

        tag_vec = self._tag_histogram(all_tags)
        class_vec = self._class_fingerprint(all_tags)
        depth_vec = self._dom_depth_stats(all_tags)
        attr_vec = self._attribute_pattern_counts(all_tags)

        embedding = tag_vec + class_vec + depth_vec + attr_vec
        return self._l2_normalise(embedding)

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """
        Compute the cosine similarity between two vectors.

        Returns:
            A float in [-1, 1].  For our use-case the values are always ≥ 0
            because all feature dimensions are non-negative.
        """
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)

    # ── feature extractors ──────────────────────────────────

    def _tag_histogram(self, tags) -> List[float]:
        """Normalised frequency of each tag in ``TAG_VOCABULARY``."""
        counts = Counter(tag.name for tag in tags)
        total = len(tags) or 1
        return [counts.get(t, 0) / total for t in TAG_VOCABULARY]

    def _class_fingerprint(self, tags) -> List[float]:
        """
        Hash every CSS class name into one of ``CLASS_BUCKETS`` bins.
        The resulting histogram captures *which layout classes* are present
        without being sensitive to their exact names.
        """
        buckets = [0.0] * CLASS_BUCKETS
        total_classes = 0
        for tag in tags:
            classes = tag.get("class", [])
            for cls in classes:
                bucket = xxhash.xxh32(cls.encode("utf-8", errors="ignore")).intdigest() % CLASS_BUCKETS
                buckets[bucket] += 1
                total_classes += 1
        # normalise
        if total_classes > 0:
            buckets = [b / total_classes for b in buckets]
        return buckets

    def _dom_depth_stats(self, tags) -> List[float]:
        """Return [max_depth, mean_depth] of the DOM tree (normalised by 100)."""
        depths = []
        for tag in tags:
            depth = len(list(tag.parents)) - 1  # subtract the [document] root
            depths.append(max(depth, 0))
        max_d = max(depths) if depths else 0
        mean_d = sum(depths) / len(depths) if depths else 0
        # normalise to keep scale comparable to the 0-1 histogram values
        return [max_d / 100.0, mean_d / 100.0]

    def _attribute_pattern_counts(self, tags) -> List[float]:
        """
        Count how many elements carry each of: id, name, type, placeholder.
        Normalised by total element count.
        """
        total = len(tags) or 1
        id_count = sum(1 for t in tags if t.get("id"))
        name_count = sum(1 for t in tags if t.get("name"))
        type_count = sum(1 for t in tags if t.get("type"))
        placeholder_count = sum(1 for t in tags if t.get("placeholder"))
        return [
            id_count / total,
            name_count / total,
            type_count / total,
            placeholder_count / total,
        ]

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _l2_normalise(vec: List[float]) -> List[float]:
        """Unit-length normalisation so cosine similarity = dot product."""
        mag = math.sqrt(sum(x * x for x in vec))
        if mag == 0.0:
            return vec
        return [x / mag for x in vec]


# Shared instance
structural_embedding = StructuralEmbedding()
