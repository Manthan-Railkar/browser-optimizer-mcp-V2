import pytest
import time
from typing import Dict, Any

from browser_optimizer.cache.cache import SemanticCache
from browser_optimizer.cache.db import macro_store
from browser_optimizer.server.main import extract_context, execute_action, replay_skill, resume_skill
from browser_optimizer.browser.manager import manager
from browser_optimizer.executor.executor import executor as action_executor


@pytest.fixture(autouse=True)
def clean_databases(monkeypatch):
    """Clear database entries and mock Playwright dependencies to run browserless tests."""
    from browser_optimizer.cache.cache import semantic_cache
    semantic_cache.clear()
    
    # Clean macros table
    import sqlite3
    with sqlite3.connect("cache.db") as conn:
        conn.execute("DELETE FROM macros")
        conn.commit()

    # Mock manager.get_page()
    class DummyPage:
        url = "https://example.com/login"
        async def title(self):
            return "Login Page"
        async def wait_for_load_state(self, state, timeout=None):
            pass
        async def content(self):
            return "<html><head><title>Login Page</title></head><body><button>Login</button></body></html>"

    async def mock_get_page(session_id="default"):
        return DummyPage()

    async def mock_navigate(url, session_id="default"):
        return DummyPage()

    monkeypatch.setattr(manager, "get_page", mock_get_page)
    monkeypatch.setattr(manager, "navigate", mock_navigate)

    # Mock action_executor.execute to behave deterministically based on action/selector
    async def mock_execute(page, action, selector, value, session_id="default"):
        if selector == "#nonexistent":
            return {"success": False, "message": "Selector not found"}
        return {"success": True, "message": "Action executed successfully"}

    monkeypatch.setattr(action_executor, "execute", mock_execute)

    yield


def test_page_cache_confidence_decay_and_routing():
    """Test that page cache confidence starts at 0.8, decays on failure, and gets bypassed if < 0.3."""
    from browser_optimizer.cache.cache import semantic_cache

    url = "https://example.com/login"
    html = "<html><head><title>Login</title></head><body><button>Login</button></body></html>"
    context = {"ui": [{"tag": "button", "text": "Login"}], "title": "Login"}

    # Store in cache
    semantic_cache.store(url, html, context)

    # 1. Verify initial confidence is 0.8
    entry = semantic_cache._cache.get(url)
    assert entry is not None
    assert abs(entry.get("confidence", 0.0) - 0.8) < 1e-5

    # 2. Decay confidence on failure (simulate step failure on the page)
    # 0.8 - 0.3 = 0.5 (verification range)
    semantic_cache.update_confidence(url, success=False)
    entry = semantic_cache._cache.get(url)
    assert entry is not None
    assert abs(entry.get("confidence", 0.0) - 0.5) < 1e-5

    # 3. Decay again to drop below 0.3
    # 0.5 - 0.3 = 0.2 (low confidence range)
    semantic_cache.update_confidence(url, success=False)
    entry = semantic_cache._cache.get(url)
    assert entry is not None
    assert abs(entry.get("confidence", 0.0) - 0.2) < 1e-5

    # 4. Lookup should now return None because confidence is < 0.3, bypassing cache
    res = semantic_cache.lookup(url, html)
    assert res is None


def test_page_cache_verification_range():
    """Test that page cache hit in verification range (0.3 <= confidence < 0.7) performs verification."""
    from browser_optimizer.cache.cache import semantic_cache

    url = "https://example.com/login"
    html = "<html><head><title>Login Page</title></head><body><button>Login</button></body></html>"
    context = {"ui": [{"tag": "button", "text": "Login"}], "title": "Login Page"}

    # Store in cache (starts at 0.8)
    semantic_cache.store(url, html, context)

    # Force confidence into verification range (0.8 - 0.3 = 0.5)
    semantic_cache.update_confidence(url, success=False)

    # Exact lookup via lookup() directly returns the entry with confidence
    res = semantic_cache.lookup(url, html)
    assert res is not None
    assert abs(res.get("confidence", 0.0) - 0.5) < 1e-5


def test_macro_confidence_growth_and_decay():
    """Test macro confidence starts at 0.8, grows on success, and decays on failure."""
    macro_id = macro_store.save_macro("Test Skill", "LOGIN", [{"action": "click", "selector": "#login"}])

    # 1. Verify initial confidence is 0.8
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert abs(macro.get("confidence", 0.0) - 0.8) < 1e-5

    # 2. Update confidence on success: 0.8 + 0.05 = 0.85
    macro_store.update_confidence(macro_id, success=True)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert abs(macro.get("confidence", 0.0) - 0.85) < 1e-5

    # 3. Update confidence on failure: 0.85 - 0.3 = 0.55
    macro_store.update_confidence(macro_id, success=False)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert abs(macro.get("confidence", 0.0) - 0.55) < 1e-5

    # 4. Cap at 1.0 test
    for _ in range(10):
        macro_store.update_confidence(macro_id, success=True)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert macro.get("confidence") == 1.0

    # 5. Cap at 0.0 test
    for _ in range(5):
        macro_store.update_confidence(macro_id, success=False)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert macro.get("confidence") == 0.0


@pytest.mark.anyio
async def test_macro_gating_and_suspension_flow():
    """Test macro replay gating (<0.3), suspension on failure, and resumption."""
    # Create macro with 2 steps: one succeeds, one fails
    sequence = [
        {"action": "wait", "selector": None, "value": "10"}, # succeeds
        {"action": "click", "selector": "#nonexistent", "value": None} # fails
    ]
    macro_id = macro_store.save_macro("Complex Skill", "DASHBOARD", sequence)

    # 1. Replay skill (first step succeeds, second fails)
    res = await replay_skill(macro_id, {})
    assert res["success"] is False
    assert "Macro failed at step 1" in res["message"]
    assert res["failed_step_index"] == 1

    # 2. Check that replay is suspended at next step (index 2)
    from browser_optimizer.server import main as server_main
    assert "default" in server_main.suspended_replays
    assert server_main.suspended_replays["default"]["macro_id"] == macro_id
    assert server_main.suspended_replays["default"]["next_step_index"] == 2

    # 3. Verify confidence dropped to 0.5 (0.8 - 0.3)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert abs(macro["confidence"] - 0.5) < 1e-5

    # 4. Resume skill. Since next_step_index == 2 is end of sequence, it should complete successfully
    resume_res = await resume_skill({})
    assert resume_res["success"] is True
    assert "Successfully finished replaying" in resume_res["message"]
    assert "default" not in server_main.suspended_replays

    # 5. Check confidence grew to 0.55 (0.5 + 0.05)
    macro = macro_store.get_macro(macro_id)
    assert macro is not None
    assert abs(macro["confidence"] - 0.55) < 1e-5

    # 6. Force confidence below 0.3 to test gating
    macro_store.update_confidence(macro_id, success=False) # 0.55 - 0.3 = 0.25
    res = await replay_skill(macro_id, {})
    assert res["success"] is False
    assert "confidence is too low" in res["message"]
