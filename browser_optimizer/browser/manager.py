"""
Browser management module using Playwright.
Handles launching, session contexts, page management, and teardown.
"""

from typing import Dict, Optional, Tuple
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from browser_optimizer.config.settings import settings
from browser_optimizer.utils.logger import logger


class BrowserManager:
    """
    Manages the lifecycle of a Playwright browser instance and standard page contexts
    mapped by session_id to support isolated concurrent execution.
    """
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.sessions: Dict[str, Tuple[BrowserContext, Page]] = {}

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
        Closes active pages and contexts across all sessions, then shuts down the browser.
        """
        logger.info("Stopping Browser...")
        # Close all active sessions
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.sessions.clear()
        logger.info("Chromium Stopped")

    async def get_page(self, session_id: str = "default") -> Page:
        """
        Retrieve the page context for the specified session_id.
        Creates a new context and page if none exists, or if the page has been closed.
        
        Returns:
            Page: Isolated Playwright page object ready for automation.
        """
        if session_id not in self.sessions or self.sessions[session_id][1].is_closed():
            if self.browser is None:
                raise RuntimeError("Browser not started. Call start() first.")
            logger.info(f"Initializing new isolated BrowserContext for session: {session_id}")
            context = await self.browser.new_context()
            page = await context.new_page()
            self.sessions[session_id] = (context, page)
        return self.sessions[session_id][1]

    async def navigate(self, url: str, session_id: str = "default"):
        """
        Navigate to a specific URL and wait for DOM load completion in the given session.
        
        Args:
            url (str): Target web application link.
            session_id (str): Target session ID.
            
        Returns:
            Page: Loaded page object.
        """
        page = await self.get_page(session_id)
        await page.goto(url, timeout=settings.BROWSER_TIMEOUT, wait_until="domcontentloaded")
        return page

    async def close_session(self, session_id: str):
        """
        Close page and BrowserContext for a specific session.
        """
        if session_id in self.sessions:
            logger.info(f"Closing BrowserContext for session: {session_id}")
            context, page = self.sessions[session_id]
            try:
                if not page.is_closed():
                    await page.close()
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing session {session_id}: {e}")
            self.sessions.pop(session_id, None)


# Shared manager instance
manager = BrowserManager()