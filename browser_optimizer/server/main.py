import asyncio
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP

from browser_optimizer.config.settings import settings
from browser_optimizer.utils.logger import logger
from browser_optimizer.browser.manager import manager
from browser_optimizer.extractor.extractor import extractor
from browser_optimizer.compressor.compressor import compressor
from browser_optimizer.classifier.classifier import classifier as page_classifier
from browser_optimizer.cache.cache import semantic_cache
from browser_optimizer.diff.diff import difference_engine
from browser_optimizer.executor.executor import executor as action_executor
from browser_optimizer.metrics.metrics import metrics

# Initialize FastMCP Server
mcp = FastMCP("Browser Optimization MCP")


async def startup():
    """Start browser session on server startup."""
    logger.info("Initializing Browser Optimizer MCP server...")
    logger.info(f"Headless Mode: {settings.HEADLESS}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    await manager.start()
    logger.info("Server startup complete. Browser ready.")


async def shutdown():
    """Clean up browser session on server shutdown."""
    logger.info("Shutting down Browser Optimizer MCP server...")
    await manager.stop()
    logger.info("Server shutdown complete.")


@mcp.tool()
async def extract_context(url: str) -> Dict[str, Any]:
    """
    Navigate to a URL, extract HTML and accessibility tree, compress context to essential UI elements,
    classify the page, cache the result, and return the optimized context.
    """
    try:
        # 1. Get page and check cache if enabled
        page = await manager.get_page()
        
        # If page is already on this URL, we can grab its content directly to check cache.
        # Otherwise, navigate first.
        if page.url != url:
            page = await manager.navigate(url)
            
        html = await page.content()
        
        # Check cache
        cached_context = semantic_cache.lookup(url, html)
        if cached_context:
            metrics.record_cache_hit()
            # Still run classifier to keep output structure consistent
            classification = page_classifier.classify(cached_context)
            return {
                "url": url,
                "title": cached_context.get("title", ""),
                "ui": cached_context.get("ui", []),
                "ax_tree": cached_context.get("ax_tree"),
                "classification": classification,
                "from_cache": True,
                "compression_ratio_pct": cached_context.get("compression_ratio", 0)
            }
            
        # Cache miss
        metrics.record_cache_miss()
        
        # 2. Extract context
        extracted = await extractor.extract(page)
        
        # 3. Compress context
        compressed = compressor.compress(extracted)
        
        # 4. Classify page
        classification = page_classifier.classify(compressed)
        
        # 5. Cache result
        semantic_cache.store(url, html, compressed)
        
        # 6. Record metrics
        metrics.record_compression(extracted["raw_html_length"], compressed["compressed_length"])
        
        return {
            "url": url,
            "title": compressed["title"],
            "ui": compressed["ui"],
            "ax_tree": compressed["ax_tree"],
            "classification": classification,
            "from_cache": False,
            "compression_ratio_pct": compressed["compression_ratio"]
        }
    except Exception as e:
        logger.error(f"Error in extract_context: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def page_diff(url: str) -> Dict[str, Any]:
    """
    Extract the current page's context and return only the changes (added/removed/changed elements)
    since the last observation of this URL.
    """
    try:
        # Extract fresh context or fetch from cache
        context = await extract_context(url)
        if not context.get("success", True):
            return context
            
        ui_elements = context.get("ui", [])
        
        # Compute differences
        diff_result = difference_engine.compute_diff(url, ui_elements)
        return diff_result
    except Exception as e:
        logger.error(f"Error in page_diff: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def execute_action(action: str, selector: Optional[str] = None, value: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a browser action (click, type, select, scroll, wait, navigate) using Playwright.
    """
    try:
        page = await manager.get_page()
        result = await action_executor.execute(page, action, selector, value)
        
        if result.get("success"):
            metrics.record_action()
            
        return result
    except Exception as e:
        logger.error(f"Error in execute_action: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def summarize_page(url: str) -> Dict[str, Any]:
    """
    Produce a concise semantic summary of the page, including its title, purpose,
    number of interactive elements, and main textual content.
    """
    try:
        # Get page context (cache-friendly)
        context = await extract_context(url)
        if not context.get("success", True):
            return context
            
        ui = context.get("ui", [])
        title = context.get("title", "")
        page_type = context.get("classification", {}).get("page_type", "unknown")
        
        # Categorize UI elements
        buttons = sum(1 for el in ui if el.get("tag") == "button")
        inputs = sum(1 for el in ui if el.get("tag") in ["input", "textarea"])
        selects = sum(1 for el in ui if el.get("tag") == "select")
        links = sum(1 for el in ui if el.get("tag") == "a")
        
        # Retrieve raw text if cached
        cached = semantic_cache.lookup(url, "")  # Simple cache lookup
        text_snippet = ""
        if cached:
            text_snippet = cached.get("text_content", "")[:300]
            
        summary = (
            f"This is a {page_type.upper()} page titled '{title}' located at {url}. "
            f"It contains {len(ui)} interactive element(s): {buttons} button(s), "
            f"{inputs} input field(s), {selects} dropdown(s), and {links} link(s). "
        )
        if text_snippet:
            summary += f"Content snippet: '{text_snippet}...'"
            
        return {
            "url": url,
            "title": title,
            "page_type": page_type,
            "summary": summary,
            "element_counts": {
                "buttons": buttons,
                "inputs": inputs,
                "selects": selects,
                "links": links
            }
        }
    except Exception as e:
        logger.error(f"Error in summarize_page: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def classify_page(url: str) -> Dict[str, Any]:
    """
    Examine the page and determine its category (e.g. login, product, search, checkout, survey, dashboard).
    """
    try:
        context = await extract_context(url)
        if not context.get("success", True):
            return context
            
        return context.get("classification", {"page_type": "unknown", "scores": {}})
    except Exception as e:
        logger.error(f"Error in classify_page: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def wait_until_ready(url: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    Navigate to a page and wait for the DOM content to be loaded and network to stabilize.
    """
    try:
        page = await manager.get_page()
        wait_timeout = timeout or settings.BROWSER_TIMEOUT
        
        logger.info(f"Navigating to {url} and waiting up to {wait_timeout}ms for readiness...")
        await page.goto(url, timeout=wait_timeout, wait_until="networkidle")
        
        return {"success": True, "message": "Page is stable and loaded.", "url": page.url}
    except Exception as e:
        logger.error(f"Error in wait_until_ready: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def cache_lookup(url: str) -> Dict[str, Any]:
    """
    Lookup a URL directly in the cache to check if we already have compressed context stored.
    """
    try:
        # Lookup using an empty string since we don't have the current live HTML
        cached_entry = semantic_cache._cache.get(url)
        if cached_entry:
            return {
                "cached": True,
                "url": url,
                "context": cached_entry.get("context"),
                "timestamp": cached_entry.get("timestamp")
            }
        return {"cached": False, "message": "No cache entry found for URL."}
    except Exception as e:
        logger.error(f"Error in cache_lookup: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_metrics() -> Dict[str, Any]:
    """
    Retrieve performance and token optimization metrics.
    """
    return metrics.get_stats()


async def main():
    await startup()
    try:
        await mcp.run_stdio_async()
    finally:
        await shutdown()


if __name__ == "__main__":
    logger.info("Starting the Browser Optimizer MCP Server...")
    import asyncio
    asyncio.run(main())
