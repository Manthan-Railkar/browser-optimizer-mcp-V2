"""
Page data extraction module.
Extracts HTML raw source, parses it via BeautifulSoup, and gets ARIA accessibility trees.
"""

from browser_optimizer.utils.logger import logger
from bs4 import BeautifulSoup


class PageExtractor:
    """
    Handles fetching raw text contents and semantic structure configurations from a Playwright Page.
    """

    async def extract_html(self, page):
        """
        Extract the raw HTML source of the page.
        
        Args:
            page (Page): Active Playwright page context.
            
        Returns:
            str: Raw HTML markup string.
        """
        logger.info("Extracting HTML...")
        html = await page.content()
        return html

    def parse_html(self, html):
        """
        Parse raw HTML content using BeautifulSoup and lxml parser.
        
        Args:
            html (str): Raw HTML string.
            
        Returns:
            BeautifulSoup: Parsed BeautifulSoup object.
        """
        soup = BeautifulSoup(html, "lxml")
        return soup

    async def extract_ax_tree(self, page):
        """
        Generate the ARIA accessibility tree structure (snapshot) of the page body.
        
        Args:
            page (Page): Active Playwright page context.
            
        Returns:
            str: YAML-like ARIA snapshot string, or None if failed.
        """
        logger.info("Extracting Accessibility Tree...")
        try:
            ax_tree = await page.locator("body").aria_snapshot()
            return ax_tree
        except Exception as e:
            logger.warning(f"Failed to extract ARIA snapshot: {e}")
            return None

    async def extract(self, page):
        """
        Run the complete extraction pipeline on a page.
        
        Args:
            page (Page): Active Playwright page context.
            
        Returns:
            dict: Package containing BeautifulSoup parsed DOM, ARIA snapshot, url, and title.
        """
        html = await self.extract_html(page)
        soup = self.parse_html(html)
        ax_tree = await self.extract_ax_tree(page)

        return {
            "html": soup,
            "ax_tree": ax_tree,
            "raw_html_length": len(html),
            "url": page.url,
            "title": await page.title()
        }


# Shared extractor instance
extractor = PageExtractor()