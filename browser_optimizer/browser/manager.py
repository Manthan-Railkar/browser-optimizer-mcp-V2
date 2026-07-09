"""
Browser management module using Playwright.
Handles launching, session contexts, page management, and teardown.
"""

from playwright.async_api import async_playwright
from browser_optimizer.config.settings import settings
from browser_optimizer.utils.logger import logger


class BrowserManager:
    """
    Manages the lifecycle of a Playwright browser instance and standard page contexts.
    Implements single-page reuse and navigation abstractions.
    """
    def __init__(self):
        self.playwright = None
        self.browser = None
        self._page = None

    async def start(self):
        """
        Launch the Chromium instance in headless/headed mode according to settings.
        Initializes the async Playwright driver.
        """
        logger.info("Starting Browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=settings.HEADLESS
        )
        logger.info("Chromium Started")

    async def stop(self):
        """
        Closes active pages and shuts down the Chromium browser session.
        Stops the Playwright execution loop.
        """
        logger.info("Stopping Browser...")
        if self._page and not self._page.is_closed():
            await self._page.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._page = None
        logger.info("Chromium Stopped")

    async def get_page(self):
        """
        Retrieve the current open page, or initialize a new context and page if none exists
        or if the current page has been closed.
        
        Returns:
            Page: Playwright page object ready for automation.
        """
        if self._page is None or self._page.is_closed():
            context = await self.browser.new_context()
            self._page = await context.new_page()
        return self._page

    async def navigate(self, url):
        """
        Navigate to a specific URL and wait for DOM load completion.
        
        Args:
            url (str): Target web application link.
            
        Returns:
            Page: Loaded page object.
        """
        page = await self.get_page()
        await page.goto(url, timeout=settings.BROWSER_TIMEOUT, wait_until="domcontentloaded")
        return page


# Shared manager instance
manager = BrowserManager()