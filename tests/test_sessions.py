import pytest
from typing import Dict, Any

from browser_optimizer.browser.manager import manager
from browser_optimizer.executor.executor import executor as action_executor
from browser_optimizer.server.main import (
    extract_context,
    execute_action,
    replay_skill,
    resume_skill,
    start_macro_recording,
    save_macro,
    close_session
)
from browser_optimizer.cache.db import macro_store


@pytest.fixture(autouse=True)
def clean_database_and_sessions(monkeypatch):
    """Clean all session state and database entries between tests, and mock Playwright for fast execution."""
    from browser_optimizer.cache.cache import semantic_cache
    semantic_cache.clear()

    # Clear active sessions in manager
    manager.sessions.clear()

    # Mock browser and context for browserless testing
    class DummyBrowser:
        async def new_context(self):
            class DummyContext:
                async def new_page(self):
                    class DummyPage:
                        url = "about:blank"
                        is_closed_flag = False
                        async def goto(self, url, timeout=None, wait_until=None):
                            self.url = url
                        async def content(self):
                            return "<html><body>Hello</body></html>"
                        async def title(self):
                            return "Dummy Page"
                        def is_closed(self):
                            return self.is_closed_flag
                        async def close(self):
                            self.is_closed_flag = True
                        async def wait_for_load_state(self, state, timeout=None):
                            pass
                        async def wait_for_selector(self, selector, timeout=None):
                            if selector == "#fail":
                                raise Exception("Selector not found")
                        async def click(self, selector):
                            pass
                        async def fill(self, selector, value):
                            pass
                        async def select_option(self, selector, value=None):
                            pass
                        async def evaluate(self, script):
                            pass
                        async def wait_for_timeout(self, timeout):
                            pass
                    return DummyPage()
                async def close(self):
                    pass
            return DummyContext()

    manager.browser = DummyBrowser()

    # Clean macros table
    import sqlite3
    with sqlite3.connect("cache.db") as conn:
        conn.execute("DELETE FROM macros")
        conn.commit()

    yield
    # Clean up again at teardown
    manager.sessions.clear()


@pytest.mark.anyio
async def test_session_isolation():
    """Test that different session IDs run in completely isolated contexts."""
    page_default = await manager.get_page("default")
    page_custom = await manager.get_page("custom")

    # Assert they are distinct objects
    assert page_default is not page_custom

    # Navigate default session
    await manager.navigate("https://default.com", "default")
    assert page_default.url == "https://default.com"
    assert page_custom.url == "about:blank"

    # Close custom session
    await manager.close_session("custom")
    assert "custom" not in manager.sessions
    assert "default" in manager.sessions
    assert page_default.is_closed() is False


@pytest.mark.anyio
async def test_session_isolated_recording():
    """Test that recording actions in one session does not contaminate or bleed into another session."""
    # Start recording on session A
    await start_macro_recording("sessionA")
    assert action_executor.is_recording("sessionA") is True
    assert action_executor.is_recording("sessionB") is False

    # Execute action on session A (should be recorded in session A)
    await execute_action("click", "#btnA", None, "sessionA")

    # Execute action on session B (should not be recorded anywhere)
    await execute_action("click", "#btnB", None, "sessionB")

    # Save macro on session A
    res = await save_macro("MacroA", "PAGE", {}, "sessionA")
    assert res["success"] is True
    
    # Verify saved macro contains only session A's step
    macro = macro_store.get_macro(res["macro_id"])
    assert len(macro["sequence"]) == 1
    assert macro["sequence"][0]["selector"] == "#btnA"


@pytest.mark.anyio
async def test_session_isolated_suspension_states():
    """Test that separate sessions can maintain independent macro suspension states concurrently."""
    # Create macro with failing second step
    sequence = [
        {"action": "click", "selector": "#ok", "value": None},
        {"action": "click", "selector": "#fail", "value": None}
    ]
    macro_id = macro_store.save_macro("Failing Macro", "TEST", sequence)

    # Replay on session A -> fails on second step -> suspends
    res_a = await replay_skill(macro_id, {}, session_id="sessionA")
    assert res_a["success"] is False
    assert res_a["failed_step_index"] == 1

    # Replay on session B -> fails on second step -> suspends
    res_b = await replay_skill(macro_id, {}, session_id="sessionB")
    assert res_b["success"] is False
    assert res_b["failed_step_index"] == 1

    from browser_optimizer.server.main import suspended_replays
    assert "sessionA" in suspended_replays
    assert "sessionB" in suspended_replays

    # Resume session A
    resume_a = await resume_skill({}, "sessionA")
    assert resume_a["success"] is True
    assert "sessionA" not in suspended_replays
    assert "sessionB" in suspended_replays

    # Resume session B
    resume_b = await resume_skill({}, "sessionB")
    assert resume_b["success"] is True
    assert "sessionB" not in suspended_replays
