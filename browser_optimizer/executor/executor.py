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
    """
    async def execute(self, page: Page, action: str, selector: Optional[str] = None, value: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a deterministic browser action on the current page.
        
        Args:
            page (Page): Active Playwright Page instance.
            action (str): Target action type (navigate, click, type, select, scroll, wait).
            selector (str, optional): Target element selector string (CSS/XPath/Text).
            value (str, optional): Input parameter value depending on action type.
            
        Returns:
            dict: Status report containing 'success' boolean and 'message' description.
        """
        action = action.lower().strip()
        logger.info(f"Executing action: {action} | Selector: {selector} | Value: {value}")

        try:
            if action == "navigate":
                if not value:
                    return {"success": False, "message": "Navigation requires a 'value' parameter containing the URL."}
                await page.goto(value, wait_until="domcontentloaded")
                return {"success": True, "message": f"Successfully navigated to {value}", "url": page.url}

            elif action == "click":
                if not selector:
                    return {"success": False, "message": "Click action requires a 'selector' parameter."}
                await page.wait_for_selector(selector, timeout=5000)
                await page.click(selector)
                return {"success": True, "message": f"Successfully clicked element {selector}"}

            elif action == "type" or action == "fill":
                if not selector or value is None:
                    return {"success": False, "message": "Type/Fill action requires both 'selector' and 'value' parameters."}
                await page.wait_for_selector(selector, timeout=5000)
                await page.fill(selector, value)
                return {"success": True, "message": f"Successfully typed '{value}' into {selector}"}

            elif action == "select":
                if not selector or not value:
                    return {"success": False, "message": "Select action requires both 'selector' and 'value' parameters."}
                await page.wait_for_selector(selector, timeout=5000)
                await page.select_option(selector, value=value)
                return {"success": True, "message": f"Successfully selected option '{value}' in {selector}"}

            elif action == "scroll":
                direction = (value or "down").lower().strip()
                if direction == "up":
                    await page.evaluate("window.scrollBy(0, -500)")
                else:
                    await page.evaluate("window.scrollBy(0, 500)")
                return {"success": True, "message": f"Successfully scrolled {direction}"}

            elif action == "wait":
                wait_time = int(value or "1000")
                await page.wait_for_timeout(wait_time)
                return {"success": True, "message": f"Successfully waited for {wait_time}ms"}

            else:
                return {"success": False, "message": f"Unknown action: {action}"}

        except Exception as e:
            error_msg = f"Failed to execute action '{action}' on '{selector or value}': {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}

# Shared executor instance
executor = RuleBasedExecutor()

