"""
Context compression engine.
Strips out unneeded DOM nodes and extracts interactive UI elements to minimize token size.
"""

from bs4 import BeautifulSoup
from browser_optimizer.utils.logger import logger

# Non-essential elements to decompose
IGNORED_TAGS = {"script", "style", "footer", "header", "noscript", "svg", "iframe"}

# Interactive components to extract
IMPORTANT_TAGS = {"button", "input", "textarea", "select", "label", "form", "a"}


class ContextCompressor:
    """
    Cleans raw BeautifulSoup parsed DOM trees by removing scripts, styling, non-content blocks,
    and isolates interactable elements to reduce character size.
    """

    def clean_dom(self, soup):
        """
        Decomposes non-essential layout tags (styles, scripts, headers, footers).
        
        Args:
            soup (BeautifulSoup): Sourced page DOM.
            
        Returns:
            BeautifulSoup: Cleaned DOM.
        """
        logger.info("Cleaning DOM...")
        for tag in soup.find_all(IGNORED_TAGS):
            tag.decompose()
        return soup

    def remove_empty(self, soup):
        """
        Recursively decompose empty tag nodes that have no text and no children.
        
        Args:
            soup (BeautifulSoup): Cleaned DOM.
            
        Returns:
            BeautifulSoup: Stripped DOM.
        """
        for tag in soup.find_all():
            if not tag.get_text(strip=True) and not tag.find():
                tag.decompose()
        return soup

    def extract_ui(self, soup):
        """
        Isolate interactable tags and compile their key descriptors (id, name, text, placeholder, type).
        
        Args:
            soup (BeautifulSoup): Stripped DOM.
            
        Returns:
            list: List of dict objects representing UI elements.
        """
        ui = []
        for tag in soup.find_all(IMPORTANT_TAGS):
            ui.append({
                "tag": tag.name,
                "text": tag.get_text(strip=True),
                "id": tag.get("id"),
                "name": tag.get("name"),
                "placeholder": tag.get("placeholder"),
                "type": tag.get("type"),
                "href": tag.get("href") if tag.name == "a" else None
            })
        return ui

    def compress(self, extracted):
        """
        Execute the DOM optimization pipeline.
        Strips DOM, extracts UI, compiles raw clean body text, and calculates compression ratios.
        
        Args:
            extracted (dict): Payload from PageExtractor containing html, ax_tree, url, and title.
            
        Returns:
            dict: Structured compressed context payload.
        """
        soup = extracted["html"]
        ax_tree = extracted["ax_tree"]
        raw_html_length = extracted.get("raw_html_length", 0)

        soup = self.clean_dom(soup)
        soup = self.remove_empty(soup)
        ui = self.extract_ui(soup)

        # body text after cleaning (for summaries)
        body = soup.find("body")
        text_content = body.get_text(separator=" ", strip=True) if body else ""

        compressed = {
            "ui": ui,
            "ax_tree": ax_tree,
            "url": extracted.get("url", ""),
            "title": extracted.get("title", ""),
            "text_content": text_content[:2000],  # cap at 2000 chars
            "raw_html_length": raw_html_length,
            "compressed_length": len(str(ui))
        }

        ratio = 0
        if raw_html_length > 0:
            ratio = round((1 - compressed["compressed_length"] / raw_html_length) * 100, 1)
        compressed["compression_ratio"] = ratio

        logger.info(f"Compressed: {raw_html_length} -> {compressed['compressed_length']} bytes ({ratio}% reduction)")
        return compressed


# Shared compressor instance
compressor = ContextCompressor()