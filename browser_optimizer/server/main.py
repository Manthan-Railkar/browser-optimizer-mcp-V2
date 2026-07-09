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
from browser_optimizer.cache.db import macro_store
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

    Cache strategy:
      1. Exact hash hit  → return cached context directly.
      2. Semantic hit     → extract fresh UI elements but reuse cached classification.
      3. Full miss        → full extract → compress → classify pipeline.
    """
    try:
        # 1. Get page and check cache if enabled
        page = await manager.get_page()

        # If page is already on this URL, we can grab its content directly to check cache.
        # Otherwise, navigate first.
        if page.url != url:
            page = await manager.navigate(url)

        html = await page.content()

        # Check cache (exact hash first, then semantic similarity fallback)
        cached_context = semantic_cache.lookup(url, html)

        if cached_context:
            confidence = cached_context.get("confidence", 0.8)
            if confidence < 0.3:
                logger.info(f"Cache entry confidence too low ({confidence:.2f} < 0.3). Skipping cache reuse.")
                cached_context = None
            elif 0.3 <= confidence < 0.7:
                logger.info(f"Cache entry confidence in verification range ({confidence:.2f}). Verifying expected page state...")
                current_title = await page.title()
                if current_title != cached_context.get("title", ""):
                    logger.warning(
                        f"Cache verification failed: Title mismatch. Expected '{cached_context.get('title')}', "
                        f"got '{current_title}'. Skipping reuse."
                    )
                    semantic_cache.update_confidence(url, success=False)
                    cached_context = None
                else:
                    logger.info("Cache verification succeeded: Title matches.")

        if cached_context:
            is_semantic = cached_context.get("semantic_match", False)

            if not is_semantic:
                # ── Exact hash hit ────────────────────────────────
                metrics.record_cache_hit()
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
            else:
                # ── Semantic similarity hit ────────────────────────
                # Structure is the same template, but text/IDs differ.
                # Extract fresh UI elements, but reuse cached classification.
                metrics.record_semantic_hit()
                similarity_score = cached_context.get("similarity_score", 0)

                extracted = await extractor.extract(page)
                compressed = compressor.compress(extracted)

                # Reuse the cached classification (same structural template)
                classification = page_classifier.classify(cached_context)

                # Store this new variant so future exact matches also hit
                semantic_cache.store(url, html, compressed)

                metrics.record_compression(
                    extracted["raw_html_length"], compressed["compressed_length"]
                )

                return {
                    "url": url,
                    "title": compressed["title"],
                    "ui": compressed["ui"],
                    "ax_tree": compressed["ax_tree"],
                    "classification": classification,
                    "from_cache": False,
                    "from_semantic_cache": True,
                    "similarity_score": similarity_score,
                    "compression_ratio_pct": compressed["compression_ratio"]
                }

        # ── Full cache miss ───────────────────────────────────
        metrics.record_cache_miss()

        # 2. Extract context
        extracted = await extractor.extract(page)

        # 3. Compress context
        compressed = compressor.compress(extracted)

        # 4. Classify page
        classification = page_classifier.classify(compressed)

        # 5. Cache result (with structural embedding)
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
        url_before = page.url
        result = await action_executor.execute(page, action, selector, value)
        
        if result.get("success"):
            metrics.record_action()
            semantic_cache.update_confidence(url_before, success=True)
        else:
            semantic_cache.update_confidence(url_before, success=False)
            
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


@mcp.tool()
async def start_macro_recording() -> Dict[str, Any]:
    """
    Start recording a sequence of browser actions to create a reusable skill macro.
    """
    action_executor.start_recording()
    return {"success": True, "message": "Started recording macro actions."}


@mcp.tool()
async def save_macro(name: str, page_type: str, parameters_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Stop recording and save the macro. 
    parameters_map: A dictionary of key: value mapping for parameter extraction. 
    e.g. {"username": "testuser", "password": "mypassword"}.
    The executor will replace instances of "testuser" with "{username}" in the saved sequence.
    """
    sequence = action_executor.stop_recording()
    if not sequence:
        return {"success": False, "message": "No actions recorded."}
        
    # Parameterize the sequence
    for step in sequence:
        val = step.get("value")
        if val:
            for param_key, param_value in parameters_map.items():
                if val == param_value:
                    step["value"] = f"{{{param_key}}}"
                    break
                    
    macro_id = macro_store.save_macro(name, page_type, sequence)
    return {"success": True, "macro_id": macro_id, "message": f"Macro '{name}' saved with {len(sequence)} steps."}


@mcp.tool()
async def list_skills(page_type: Optional[str] = None) -> Dict[str, Any]:
    """
    List available skill macros, optionally filtered by page_type (e.g. LOGIN).
    """
    macros = macro_store.list_macros(page_type)
    return {"success": True, "macros": macros}


# Global state for suspended macro replays
suspended_replay: Optional[Dict[str, Any]] = None


@mcp.tool()
async def replay_skill(macro_id: int, parameters: Dict[str, str]) -> Dict[str, Any]:
    """
    Replay a previously recorded macro.
    Inject parameters into the placeholders (e.g. {username}) before execution.
    """
    global suspended_replay
    macro = macro_store.get_macro(macro_id)
    if not macro:
        return {"success": False, "message": f"Macro {macro_id} not found."}
        
    confidence = macro.get("confidence", 0.8)
    if confidence < 0.3:
        return {
            "success": False,
            "message": f"Macro '{macro['name']}' confidence is too low ({confidence:.2f} < 0.3). Skipping macro replay. Please execute actions manually."
        }
        
    sequence = macro["sequence"]
    logger.info(f"Replaying macro '{macro['name']}' with confidence {confidence:.2f} and params {parameters}")
    
    page = await manager.get_page()
    
    # Temporarily disable recording if it was on
    was_recording = action_executor.recording
    action_executor.recording = False
    
    verify_steps = 0.3 <= confidence < 0.7
    
    success_count = 0
    try:
        for i, step in enumerate(sequence):
            action = step["action"]
            selector = step["selector"]
            value = step.get("value")
            
            # Inject parameters
            if value and isinstance(value, str):
                for pk, pv in parameters.items():
                    placeholder = f"{{{pk}}}"
                    if placeholder in value:
                        value = value.replace(placeholder, pv)
            
            result = await action_executor.execute(page, action, selector, value)
            if not result.get("success"):
                # Suspend macro replay
                suspended_replay = {
                    "macro_id": macro_id,
                    "next_step_index": i + 1,
                    "parameters": parameters
                }
                macro_store.update_confidence(macro_id, success=False)
                return {
                    "success": False,
                    "failed_step_index": i,
                    "failed_action": action,
                    "failed_selector": selector,
                    "message": (
                        f"Macro failed at step {i} ({action} {selector}) with error: {result.get('message')}. "
                        "Macro replay has been suspended. Please execute this step manually using execute_action, "
                        "and then call the resume_skill tool to complete the remaining steps."
                    )
                }
                
            if verify_steps:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=2000)
                except Exception:
                    pass
            success_count += 1
            
        macro_store.update_confidence(macro_id, success=True)
        if suspended_replay and suspended_replay.get("macro_id") == macro_id:
            suspended_replay = None
        return {"success": True, "message": f"Successfully replayed macro '{macro['name']}'."}
        
    finally:
        action_executor.recording = was_recording


@mcp.tool()
async def resume_skill(parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Resume a suspended macro replay from the step following the failure.
    Optional parameters can override/update parameters if needed.
    """
    global suspended_replay
    if not suspended_replay:
        return {"success": False, "message": "No suspended macro replay found."}
        
    macro_id = suspended_replay["macro_id"]
    start_index = suspended_replay["next_step_index"]
    original_parameters = suspended_replay["parameters"]
    
    # Merge parameters if new ones provided
    if parameters:
        original_parameters.update(parameters)
        
    macro = macro_store.get_macro(macro_id)
    if not macro:
        suspended_replay = None
        return {"success": False, "message": f"Macro {macro_id} not found."}
        
    sequence = macro["sequence"]
    if start_index >= len(sequence):
        macro_store.update_confidence(macro_id, success=True)
        suspended_replay = None
        return {"success": True, "message": f"Successfully finished replaying remaining steps of '{macro['name']}'."}
        
    page = await manager.get_page()
    was_recording = action_executor.recording
    action_executor.recording = False
    
    confidence = macro.get("confidence", 0.8)
    verify_steps = 0.3 <= confidence < 0.7
    
    logger.info(f"Resuming macro '{macro['name']}' from step {start_index} with params {original_parameters}")
    
    try:
        for i in range(start_index, len(sequence)):
            step = sequence[i]
            action = step["action"]
            selector = step["selector"]
            value = step.get("value")
            
            # Inject parameters
            if value and isinstance(value, str):
                for pk, pv in original_parameters.items():
                    placeholder = f"{{{pk}}}"
                    if placeholder in value:
                        value = value.replace(placeholder, pv)
                        
            result = await action_executor.execute(page, action, selector, value)
            if not result.get("success"):
                # Update suspension index to the next step
                suspended_replay["next_step_index"] = i + 1
                macro_store.update_confidence(macro_id, success=False)
                return {
                    "success": False,
                    "failed_step_index": i,
                    "failed_action": action,
                    "failed_selector": selector,
                    "message": (
                        f"Resumed step {i} ({action} {selector}) failed with error: {result.get('message')}. "
                        "Replay is suspended again. Please execute manually and run resume_skill to try the rest."
                    )
                }
                
            if verify_steps:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=2000)
                except Exception:
                    pass
                    
        # All steps completed successfully
        macro_store.update_confidence(macro_id, success=True)
        suspended_replay = None
        return {"success": True, "message": f"Successfully finished replaying remaining steps of '{macro['name']}'."}
        
    finally:
        action_executor.recording = was_recording


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
