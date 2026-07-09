"""
State Difference Engine module.
Tracks historical states of pages and computes incremental UI deltas (adds/removes).
"""

from typing import List, Dict, Any, Optional
from browser_optimizer.utils.logger import logger

class StateDifferenceEngine:
    """
    Computes differences between the currently observed UI element tree and the
    previously recorded UI state for a specific URL, returning only the deltas.
    """
    def __init__(self):
        # Maps URL to the list of elements from the last observation
        self.history: Dict[str, List[Dict[str, Any]]] = {}

    def compute_diff(self, url: str, current_ui: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare the current list of UI elements with the last observed list for a URL.
        
        Args:
            url (str): Target web address.
            current_ui (list): List of dict elements currently found on the page.
            
        Returns:
            dict: Delta report containing lists of 'added', 'removed', and 'changed' elements.
        """
        previous_ui = self.history.get(url, [])
        
        # Simple fingerprint for identifying matching elements
        def get_fingerprint(el: Dict[str, Any]) -> str:
            # Join key fields to uniquely identify the element
            tag = el.get("tag") or ""
            el_id = el.get("id") or ""
            name = el.get("name") or ""
            text = el.get("text") or ""
            placeholder = el.get("placeholder") or ""
            return f"{tag}|{el_id}|{name}|{text[:30]}|{placeholder}"

        prev_fingerprints = {get_fingerprint(el): el for el in previous_ui}
        curr_fingerprints = {get_fingerprint(el): el for el in current_ui}

        added = []
        removed = []
        changed = []

        # Find added elements
        for fp, el in curr_fingerprints.items():
            if fp not in prev_fingerprints:
                added.append(el)

        # Find removed elements
        for fp, el in prev_fingerprints.items():
            if fp not in curr_fingerprints:
                removed.append(el)

        # Store current state in history
        self.history[url] = current_ui
        logger.info(f"Diff computed for {url}: {len(added)} added, {len(removed)} removed")

        return {
            "url": url,
            "added": added,
            "removed": removed,
            "changed": changed  # Reserved for future deep attribute comparison
        }

    def clear_history(self, url: Optional[str] = None):
        """
        Purge the historical observations log for a specific URL or the entire session.
        
        Args:
            url (str, optional): Target URL to clear. If None, purges all URLs.
        """
        if url:
            self.history.pop(url, None)
        else:
            self.history.clear()

# Shared difference engine instance
difference_engine = StateDifferenceEngine()

