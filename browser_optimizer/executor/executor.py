"""
Rule-Based Action Executor module.
Translates structured agent commands directly into Playwright browser interactions.
"""

from playwright.async_api import Page
from typing import Dict, Any, Optional
from browser_optimizer.utils.logger import logger

class RuleBasedExecutor:
    """
    Executes standard actions directly on a Playwright Page.
    Handles selectors, keystrokes, drop-down options, scrolling, and waits with automated timeouts.
    Supports session-isolated recording.
    """
    def __init__(self):
        self.recordings = {}  # dict of session_id: list of steps

    def start_recording(self, session_id: str = "default"):
        """Start recording actions for a specific session."""
        self.recordings[session_id] = []

    def stop_recording(self, session_id: str = "default") -> list:
        """Stop recording and return the recorded sequence for a specific session."""
        return self.recordings.pop(session_id, [])

    def is_recording(self, session_id: str = "default") -> bool:
        """Check if recording is active for a specific session."""
        return session_id in self.recordings

    async def execute(
        self,
        page: Page,
        action: str,
        selector: Optional[str] = None,
        value: Optional[str] = None,
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Execute a deterministic browser action on the current page.
        
        Args:
            page (Page): Active Playwright Page instance.
            action (str): Target action type (navigate, click, type, select, scroll, wait).
            selector (str, optional): Target element selector string (CSS/XPath/Text).
            value (str, optional): Input parameter value depending on action type.
            session_id (str): Target session ID.
            
        Returns:
            dict: Status report containing 'success' boolean and 'message' description.
        """
        action = action.lower().strip()
        logger.info(f"Executing action: {action} | Selector: {selector} | Value: {value} | Session: {session_id}")

        result = {"success": False, "message": "Unknown error"}

        try:
            if action == "navigate":
                if not value:
                    result = {"success": False, "message": "Navigation requires a 'value' parameter containing the URL."}
                else:
                    await page.goto(value, wait_until="domcontentloaded")
                    result = {"success": True, "message": f"Successfully navigated to {value}", "url": page.url}

            elif action == "click":
                if not selector:
                    result = {"success": False, "message": "Click action requires a 'selector' parameter."}
                else:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.click(selector)
                    result = {"success": True, "message": f"Successfully clicked element {selector}"}

            elif action == "type" or action == "fill":
                if not selector or value is None:
                    result = {"success": False, "message": "Type/Fill action requires both 'selector' and 'value' parameters."}
                else:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, value)
                    result = {"success": True, "message": f"Successfully typed '{value}' into {selector}"}

            elif action == "select":
                if not selector or not value:
                    result = {"success": False, "message": "Select action requires both 'selector' and 'value' parameters."}
                else:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.select_option(selector, value=value)
                    result = {"success": True, "message": f"Successfully selected option '{value}' in {selector}"}

            elif action == "scroll":
                direction = (value or "down").lower().strip()
                if direction == "up":
                    await page.evaluate("window.scrollBy(0, -500)")
                else:
                    await page.evaluate("window.scrollBy(0, 500)")
                result = {"success": True, "message": f"Successfully scrolled {direction}"}

            elif action == "wait":
                wait_time = int(value or "1000")
                await page.wait_for_timeout(wait_time)
                result = {"success": True, "message": f"Successfully waited for {wait_time}ms"}

            else:
                result = {"success": False, "message": f"Unknown action: {action}"}

        except Exception as e:
            error_msg = f"Failed to execute action '{action}' on '{selector or value}': {str(e)}"
            logger.error(error_msg)
            result = {"success": False, "message": error_msg}

        if result.get("success") and session_id in self.recordings:
            self.recordings[session_id].append({
                "action": action,
                "selector": selector,
                "value": value
            })

        return result

# Shared executor instance
executor = RuleBasedExecutor()

