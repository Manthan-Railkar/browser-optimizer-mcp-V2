import asyncio
import json
import websockets
from typing import Dict, Any, Optional, List
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
from browser_optimizer.dashboard.server import start_dashboard_server

# Initialize FastMCP Server
mcp = FastMCP("Browser Optimization MCP")

# Push mode page watching state trackers
ws_server = None
watch_clients: Dict[str, List[Any]] = {}  # session_id -> list of websocket connections
watch_tasks: Dict[str, asyncio.Task] = {}  # session_id -> asyncio.Task for polling loop


async def websocket_handler(websocket):
    """
    Handle connection registration and lifecycle for incoming WebSocket clients.
    Clients must register by sending a JSON payload: {"action": "register", "session_id": "..."}.
    """
    try:
        # Expect first message to be a registration message
        message = await websocket.recv()
        data = json.loads(message)
        if data.get("action") == "register":
            session_id = data.get("session_id", "default")
            if session_id not in watch_clients:
                watch_clients[session_id] = []
            watch_clients[session_id].append(websocket)
            logger.info(f"WebSocket client registered for session: {session_id}")
            
            # Keep the socket open to detect client disconnection
            async for _ in websocket:
                pass
    except Exception as e:
        logger.warning(f"WebSocket client connection error: {e}")
    finally:
        # Remove from active connections
        for sid, clients in list(watch_clients.items()):
            if websocket in clients:
                clients.remove(websocket)
                logger.info(f"WebSocket client unregistered from session: {sid}")


async def poll_page_diff(url: str, interval_seconds: float, session_id: str):
    """
    Periodically poll the page diff and broadcast changes to registered WebSocket clients.
    """
    logger.info(f"Starting page watch loop for '{url}' in session '{session_id}' (interval: {interval_seconds}s)")
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                # Calculate page diff
                diff = await page_diff(url, session_id=session_id)
                # If there are registered clients, push updates
                clients = watch_clients.get(session_id, [])
                if clients:
                    payload = json.dumps(diff)
                    dead_clients = []
                    for client in clients:
                        try:
                            await client.send(payload)
                        except Exception:
                            dead_clients.append(client)
                    # Clean up any dead connections
                    for client in dead_clients:
                        if client in clients:
                            clients.remove(client)
            except Exception as e:
                logger.error(f"Error evaluating diff in page watch poller: {e}")
    except asyncio.CancelledError:
        logger.info(f"Page watch poller for '{url}' in session '{session_id}' was cancelled.")


async def startup():
    """Start browser session and WebSocket server on server startup."""
    global ws_server
    logger.info("Initializing Browser Optimizer MCP server...")
    logger.info(f"Headless Mode: {settings.HEADLESS}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    await manager.start()
    
    # Start WebSocket Server
    logger.info("Starting WebSocket Server on port 8765...")
    ws_server = await websockets.serve(websocket_handler, "localhost", 8765)
    logger.info("WebSocket Server started on ws://localhost:8765")
    logger.info("Server startup complete. Browser ready.")


async def shutdown():
    """Clean up browser session and active watchers on server shutdown."""
    global ws_server, watch_tasks
    logger.info("Shutting down Browser Optimizer MCP server...")
    
    # Cancel all running watch tasks
    for sid, task in list(watch_tasks.items()):
        logger.info(f"Cancelling active watch poller for session '{sid}'...")
        task.cancel()
    watch_tasks.clear()
    
    # Close WebSocket Server
    if ws_server:
        ws_server.close()
        await ws_server.wait_closed()
        logger.info("WebSocket Server closed.")
        
    await manager.stop()
    logger.info("Server shutdown complete.")


@mcp.tool()
async def extract_context(url: str, session_id: str = "default") -> Dict[str, Any]:
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
        page = await manager.get_page(session_id)

        # If page is already on this URL, we can grab its content directly to check cache.
        # Otherwise, navigate first.
        if page.url != url:
            page = await manager.navigate(url, session_id)

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
async def page_diff(url: str, session_id: str = "default") -> Dict[str, Any]:
    """
    Extract the current page's context and return only the changes (added/removed/changed elements)
    since the last observation of this URL.
    """
    try:
        # Extract fresh context or fetch from cache
        context = await extract_context(url, session_id=session_id)
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
async def execute_action(
    action: str,
    selector: Optional[str] = None,
    value: Optional[str] = None,
    session_id: str = "default"
) -> Dict[str, Any]:
    """
    Execute a browser action (click, type, select, scroll, wait, navigate) using Playwright.
    """
    try:
        page = await manager.get_page(session_id)
        url_before = page.url
        result = await action_executor.execute(page, action, selector, value, session_id=session_id)
        
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
async def summarize_page(url: str, session_id: str = "default") -> Dict[str, Any]:
    """
    Produce a concise semantic summary of the page, including its title, purpose,
    number of interactive elements, and main textual content.
    """
    try:
        # Get page context (cache-friendly)
        context = await extract_context(url, session_id=session_id)
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
async def classify_page(url: str, session_id: str = "default") -> Dict[str, Any]:
    """
    Examine the page and determine its category (e.g. login, product, search, checkout, survey, dashboard).
    """
    try:
        context = await extract_context(url, session_id=session_id)
        if not context.get("success", True):
            return context
            
        return context.get("classification", {"page_type": "unknown", "scores": {}})
    except Exception as e:
        logger.error(f"Error in classify_page: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def wait_until_ready(url: str, timeout: Optional[int] = None, session_id: str = "default") -> Dict[str, Any]:
    """
    Navigate to a page and wait for the DOM content to be loaded and network to stabilize.
    """
    try:
        page = await manager.get_page(session_id)
        wait_timeout = timeout or settings.BROWSER_TIMEOUT
        
        logger.info(f"Navigating to {url} and waiting up to {wait_timeout}ms for readiness...")
        await page.goto(url, timeout=wait_timeout, wait_until="networkidle")
        
        return {"success": True, "message": "Page is stable and loaded.", "url": page.url}
    except Exception as e:
        logger.error(f"Error in wait_until_ready: {str(e)}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def cache_lookup(url: str, session_id: str = "default") -> Dict[str, Any]:
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
async def start_macro_recording(session_id: str = "default") -> Dict[str, Any]:
    """
    Start recording a sequence of browser actions to create a reusable skill macro.
    """
    action_executor.start_recording(session_id)
    return {"success": True, "message": f"Started recording macro actions for session '{session_id}'."}


@mcp.tool()
async def save_macro(
    name: str,
    page_type: str,
    parameters_map: Dict[str, str],
    session_id: str = "default"
) -> Dict[str, Any]:
    """
    Stop recording and save the macro. 
    parameters_map: A dictionary of key: value mapping for parameter extraction. 
    e.g. {"username": "testuser", "password": "mypassword"}.
    The executor will replace instances of "testuser" with "{username}" in the saved sequence.
    """
    sequence = action_executor.stop_recording(session_id)
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


@mcp.tool()
async def suggest_skill(page_type: str) -> Dict[str, Any]:
    """
    Fetch the highest confidence macro for a page_type and recommend a routing strategy.
    Returns the macro and a routing_decision: 'DIRECT_REUSE', 'VERIFY_REUSE', or 'SKIP'.
    """
    macro = macro_store.get_best_macro(page_type)
    if not macro:
        return {"success": False, "routing_decision": "SKIP", "message": f"No skills found for {page_type}."}
        
    confidence = macro.get("confidence", 0.0)
    
    if confidence >= 0.7:
        routing = "DIRECT_REUSE"
        instruction = "You can blindly replay this macro."
    elif confidence >= 0.3:
        routing = "VERIFY_REUSE"
        instruction = "Replay this macro, but pass expected_url or expected_page_type to verify it worked."
    else:
        routing = "SKIP"
        instruction = "Confidence is too low. Please reason from scratch instead of reusing."
        
    return {
        "success": True,
        "routing_decision": routing,
        "instruction": instruction,
        "macro": macro
    }


# Global state for suspended macro replays per session
suspended_replays: Dict[str, Dict[str, Any]] = {}


@mcp.tool()
async def replay_skill(
    macro_id: int,
    parameters: Dict[str, str],
    expected_url: Optional[str] = None,
    expected_page_type: Optional[str] = None,
    session_id: str = "default"
) -> Dict[str, Any]:
    """
    Replay a previously recorded macro in a given session.
    Inject parameters into the placeholders (e.g. {username}) before execution.
    If expected_url or expected_page_type are provided, the system will verify the post-state and auto-decay on mismatch.
    """
    global suspended_replays
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
    logger.info(f"Replaying macro '{macro['name']}' with params {parameters} in session '{session_id}'")
    
    page = await manager.get_page(session_id)
    
    # Temporarily disable recording if it was on
    was_recording = action_executor.is_recording(session_id)
    if was_recording:
        action_executor.recordings.pop(session_id, None)
    
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
            
            result = await action_executor.execute(page, action, selector, value, session_id=session_id)
            if not result.get("success"):
                # Suspend macro replay
                suspended_replays[session_id] = {
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
            
        # Optional post-state verification
        if expected_url or expected_page_type:
            # Wait briefly for network to settle after final action
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass
                
            current_url = page.url
            if expected_url and not current_url.startswith(expected_url):
                macro_store.update_confidence(macro_id, success=False)
                return {
                    "success": False, 
                    "message": f"Verification failed: Expected URL starting with {expected_url}, but got {current_url}",
                    "failure_context": {
                        "failed_step_index": success_count,
                        "reason": "URL_MISMATCH",
                        "current_url": current_url
                    }
                }
                
            if expected_page_type:
                # Classify the new page to verify
                context = await extract_context(current_url, session_id=session_id)
                current_page_type = context.get("classification", {}).get("page_type")
                if current_page_type != expected_page_type:
                    macro_store.update_confidence(macro_id, success=False)
                    return {
                        "success": False, 
                        "message": f"Verification failed: Expected page type {expected_page_type}, but got {current_page_type}",
                        "failure_context": {
                            "failed_step_index": success_count,
                            "reason": "PAGE_TYPE_MISMATCH",
                            "current_url": current_url,
                            "current_page_type": current_page_type
                        }
                    }

        macro_store.update_confidence(macro_id, success=True)
        if session_id in suspended_replays and suspended_replays[session_id].get("macro_id") == macro_id:
            suspended_replays.pop(session_id, None)
        return {"success": True, "message": f"Successfully replayed macro '{macro['name']}'."}
        
    finally:
        if was_recording:
            action_executor.start_recording(session_id)


@mcp.tool()
async def resume_skill(parameters: Optional[Dict[str, str]] = None, session_id: str = "default") -> Dict[str, Any]:
    """
    Resume a suspended macro replay from the step following the failure for the given session.
    Optional parameters can override/update parameters if needed.
    """
    global suspended_replays
    if session_id not in suspended_replays:
        return {"success": False, "message": f"No suspended macro replay found for session '{session_id}'."}
        
    session_state = suspended_replays[session_id]
    macro_id = session_state["macro_id"]
    start_index = session_state["next_step_index"]
    original_parameters = session_state["parameters"]
    
    # Merge parameters if new ones provided
    if parameters:
        original_parameters.update(parameters)
        
    macro = macro_store.get_macro(macro_id)
    if not macro:
        suspended_replays.pop(session_id, None)
        return {"success": False, "message": f"Macro {macro_id} not found."}
        
    sequence = macro["sequence"]
    if start_index >= len(sequence):
        macro_store.update_confidence(macro_id, success=True)
        suspended_replays.pop(session_id, None)
        return {"success": True, "message": f"Successfully finished replaying remaining steps of '{macro['name']}'."}
        
    page = await manager.get_page(session_id)
    was_recording = action_executor.is_recording(session_id)
    if was_recording:
        action_executor.recordings.pop(session_id, None)
    
    confidence = macro.get("confidence", 0.8)
    verify_steps = 0.3 <= confidence < 0.7
    
    logger.info(f"Resuming macro '{macro['name']}' from step {start_index} with params {original_parameters} in session '{session_id}'")
    
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
                        
            result = await action_executor.execute(page, action, selector, value, session_id=session_id)
            if not result.get("success"):
                # Update suspension index to the next step
                session_state["next_step_index"] = i + 1
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
        suspended_replays.pop(session_id, None)
        return {"success": True, "message": f"Successfully finished replaying remaining steps of '{macro['name']}'."}
        
    finally:
        if was_recording:
            action_executor.start_recording(session_id)


@mcp.tool()
async def close_session(session_id: str) -> Dict[str, Any]:
    """
    Close page and BrowserContext for a specific session.
    """
    await manager.close_session(session_id)
    suspended_replays.pop(session_id, None)
    return {"success": True, "message": f"Session '{session_id}' has been closed."}


@mcp.tool()
async def watch_page(url: str, interval_seconds: int = 5, session_id: str = "default") -> Dict[str, Any]:
    """
    Start polling a page's visual changes at a regular interval and pushing them
    automatically to connected WebSocket clients registered for that session.
    """
    global watch_tasks
    # Cancel existing watch task for this session if any
    if session_id in watch_tasks:
        watch_tasks[session_id].cancel()
        
    # Start new task
    watch_tasks[session_id] = asyncio.create_task(poll_page_diff(url, float(interval_seconds), session_id))
    return {
        "success": True,
        "message": f"Started watching {url} in session '{session_id}' every {interval_seconds}s. Connect to ws://localhost:8765 and register with session_id '{session_id}' to receive live diff updates."
    }


@mcp.tool()
async def stop_watch_page(session_id: str = "default") -> Dict[str, Any]:
    """
    Stop the background page watch poll for the specified session.
    """
    global watch_tasks
    if session_id in watch_tasks:
        watch_tasks[session_id].cancel()
        watch_tasks.pop(session_id, None)
        return {"success": True, "message": f"Stopped watching page in session '{session_id}'."}
    return {"success": False, "message": f"No active page watch found for session '{session_id}'."}



async def main():
    await startup()
    start_dashboard_server()
    try:
        await mcp.run_stdio_async()
    finally:
        await shutdown()


if __name__ == "__main__":
    logger.info("Starting the Browser Optimizer MCP Server...")
    import asyncio
    asyncio.run(main())
