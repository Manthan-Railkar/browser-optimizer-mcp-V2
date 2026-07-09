import pytest
import asyncio
import json
import websockets
from typing import Dict, Any

from browser_optimizer.browser.manager import manager
from browser_optimizer.server.main import (
    startup,
    shutdown,
    watch_page,
    stop_watch_page,
    watch_clients,
    watch_tasks,
    page_diff,
    extract_context
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_websocket_server(monkeypatch):
    """Start the MCP startup (which spins up the websocket server) with mocked browser manager."""
    # Mock manager start/stop/get_page to be browserless
    async def mock_start():
        pass
    async def mock_stop():
        pass

    class DummyPage:
        url = "https://example.com/watch"
        async def title(self):
            return "Watch Page"
        async def wait_for_load_state(self, state, timeout=None):
            pass
        async def content(self):
            return "<html></html>"
        async def wait_for_selector(self, selector, timeout=None):
            pass
        async def click(self, selector):
            pass

    async def mock_get_page(session_id="default"):
        return DummyPage()

    monkeypatch.setattr(manager, "start", mock_start)
    monkeypatch.setattr(manager, "stop", mock_stop)
    monkeypatch.setattr(manager, "get_page", mock_get_page)

    # Mock page_diff tool to return dummy differences
    diff_counter = 0
    async def mock_page_diff(url, session_id="default"):
        nonlocal diff_counter
        diff_counter += 1
        return {
            "success": True,
            "session_id": session_id,
            "url": url,
            "added": [{"id": f"el_{diff_counter}", "tag": "button", "text": "New Button"}],
            "removed": [],
            "changed": []
        }

    monkeypatch.setattr("browser_optimizer.server.main.page_diff", mock_page_diff)

    # Clear cache
    from browser_optimizer.cache.cache import semantic_cache
    semantic_cache.clear()

    # Start the server (launches websocket server)
    await startup()

    yield

    # Teardown: shut down websocket server and clean up tasks
    await shutdown()


@pytest.mark.anyio
async def test_websocket_registration():
    """Verify that clients can connect to the websocket server and register for a session."""
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Register for custom session 'sessionX'
        reg_payload = {"action": "register", "session_id": "sessionX"}
        await ws.send(json.dumps(reg_payload))
        
        # Yield to let server process the registration message
        await asyncio.sleep(0.1)

        # Check client is registered
        assert "sessionX" in watch_clients
        assert len(watch_clients["sessionX"]) == 1


@pytest.mark.anyio
async def test_watch_page_push_updates():
    """Verify that watch_page periodic evaluation pushes visual updates to registered websocket clients."""
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Register for 'default' session
        await ws.send(json.dumps({"action": "register", "session_id": "default"}))
        await asyncio.sleep(0.1)

        # Start page watch poller with a 0.2s interval
        res = await watch_page("https://example.com/watch", interval_seconds=0.2, session_id="default")
        assert res["success"] is True

        # Wait and receive at least two pushed updates
        msg1 = await ws.recv()
        data1 = json.loads(msg1)
        assert data1["success"] is True
        assert len(data1["added"]) == 1
        assert data1["added"][0]["id"] == "el_1"

        msg2 = await ws.recv()
        data2 = json.loads(msg2)
        assert len(data2["added"]) == 1
        assert data2["added"][0]["id"] == "el_2"

        # Stop watch poller
        stop_res = await stop_watch_page("default")
        assert stop_res["success"] is True
        assert "default" not in watch_tasks


@pytest.mark.anyio
async def test_session_isolated_pushes():
    """Verify that websocket pushes are strictly isolated by session ID."""
    uri = "ws://localhost:8765"
    
    # Client A connects and registers for sessionA
    async with websockets.connect(uri) as ws_a:
        await ws_a.send(json.dumps({"action": "register", "session_id": "sessionA"}))
        
        # Client B connects and registers for sessionB
        async with websockets.connect(uri) as ws_b:
            await ws_b.send(json.dumps({"action": "register", "session_id": "sessionB"}))
            await asyncio.sleep(0.1)

            # Watch page on session A only (0.2s interval)
            await watch_page("https://example.com/watch", interval_seconds=0.2, session_id="sessionA")

            # Client A should receive updates
            msg = await ws_a.recv()
            data = json.loads(msg)
            assert data["session_id"] == "sessionA"

            # Client B should NOT receive any updates (we wait a bit to be sure)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws_b.recv(), timeout=0.5)

            # Clean up
            await stop_watch_page("sessionA")


@pytest.mark.anyio
async def test_session_replay_logging():
    """Verify that events are logged to session_replay_store during extract_context and execute_action."""
    from browser_optimizer.cache.db import session_replay_store
    from browser_optimizer.server.main import execute_action

    session_replay_store.clear_all()

    # Trigger extract_context (cache miss log)
    await extract_context("https://example.com/watch", session_id="sessionR")
    
    # Verify log entry in sessionR
    logs = session_replay_store.get_replay("sessionR")
    assert len(logs) == 1
    assert "extract_context" in logs[0]["action_taken"]
    assert logs[0]["outcome"] == "cache_miss"

    # Trigger execute_action (manual action log)
    await execute_action("click", "#btn", None, "sessionR")

    # Verify log entry
    logs = session_replay_store.get_replay("sessionR")
    assert len(logs) == 2
    assert logs[1]["action_taken"] == "click #btn"
    assert logs[1]["outcome"] == "success"


@pytest.mark.anyio
async def test_session_replay_api():
    """Verify that get_session_replay tool returns the session's logs correctly."""
    from browser_optimizer.cache.db import session_replay_store
    from browser_optimizer.server.main import get_session_replay

    session_replay_store.clear_all()
    session_replay_store.log_event("sessionT", "PRODUCT", "click #buy", 0.95, "success")

    res = await get_session_replay("sessionT")
    assert res["success"] is True
    assert res["session_id"] == "sessionT"
    assert len(res["logs"]) == 1
    assert res["logs"][0]["action_taken"] == "click #buy"
    assert res["logs"][0]["page_classification"] == "PRODUCT"
    assert res["logs"][0]["confidence_used"] == 0.95
    assert res["logs"][0]["outcome"] == "success"

